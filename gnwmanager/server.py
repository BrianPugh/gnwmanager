"""Serve serialized low-level OCDBackend operations to remote WebSocket clients."""

import asyncio
import contextlib
import json
import logging
import ssl
from concurrent.futures import ThreadPoolExecutor

from websockets.asyncio.server import serve

LOG = logging.getLogger("gnw-remote")
DEFAULT_PORT = 8765
MAX_MEMORY = 65536


class BackendSession:
    """All backend calls, including cleanup, run on one worker in request order."""

    def __init__(self, factory, frequency=None):
        self.frequency = frequency
        self.factory = factory
        self.backend = None

    def close(self):
        backend, self.backend = self.backend, None
        if backend:
            backend.close()

    def execute(self, method, args):
        arity = {
            "attach": 0,
            "read_memory": 2,
            "write_memory": 2,
            "read_register": 1,
            "write_register": 2,
            "set_frequency": 1,
            "halt": 0,
            "resume": 0,
            "reset_and_halt": 0,
        }
        if (
            not isinstance(method, str)
            or not isinstance(args, list)
            or method not in arity
            or len(args) != arity[method]
        ):
            raise ValueError("Unsupported remote adapter operation or arguments")
        if method == "attach":
            self.close()
            self.backend = self.factory()
            try:
                self.backend.open()
                if self.frequency is not None:
                    self.backend.set_frequency(self.frequency)
            except Exception as error:
                diagnostic = "\n".join(getattr(self.backend, "_stderr_buffer", []))[-2000:]
                with contextlib.suppress(Exception):
                    self.close()
                raise RuntimeError(f"No device detected: {error}\n{diagnostic}") from error
            return True
        if self.backend is None:
            raise RuntimeError("No device detected")
        backend = self.backend
        if method in ("read_memory", "write_memory"):
            addr = args[0]
            if not isinstance(addr, int) or not 0 <= addr <= 0xFFFFFFFF:
                raise ValueError("Invalid memory address")
            data = args[1] if method == "read_memory" else bytes.fromhex(args[1])
            size = data if method == "read_memory" else len(data)
            if not isinstance(size, int) or not 0 <= size <= MAX_MEMORY or addr + size > 0x100000000:
                raise ValueError("Invalid memory size")
            if method == "read_memory":
                # Aligned single words use the binding's mdw path rather than four mdbs.
                result = (
                    backend.read_uint32(addr).to_bytes(4, "little")
                    if size == 4 and addr % 4 == 0
                    else backend.read_memory(addr, size)
                )
                if len(result) != size:
                    raise RuntimeError("Short device memory read")
                return result.hex()
            backend.write_memory(addr, data)
            return None
        if method in ("read_register", "write_register"):
            name = args[0].lower()
            registers = {f"r{i}" for i in range(16)} | {
                "sp",
                "lr",
                "pc",
                "xpsr",
                "msp",
                "psp",
            }
            if name not in registers:
                raise ValueError("Unknown ARM register")
            if method == "read_register":
                return backend.read_register(name)
            value = args[1]
            if not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF:
                raise ValueError("Invalid register value")
            backend.write_register(name, value)
            return None
        if method == "set_frequency":
            frequency = args[0]
            if not isinstance(frequency, int) or not 1 <= frequency <= 10000000:
                raise ValueError("Invalid SWD frequency")
            backend.set_frequency(frequency)
            return None
        if method in ("halt", "resume", "reset_and_halt") and not args:
            getattr(backend, method)()
            return None
        raise ValueError("Unsupported remote adapter operation")


async def handle_session(ws, factory, frequency=None, backend_name="openocd"):
    session = BackendSession(factory, frequency)
    executor = ThreadPoolExecutor(max_workers=1)
    loop = asyncio.get_running_loop()
    await ws.send(
        json.dumps(
            {
                "type": "hello",
                "version": 1,
                "backend": "gnwmanager",
                "targetControl": "gdb" if backend_name == "gdb" else "arm",
            }
        )
    )
    try:
        async for message in ws:
            if isinstance(message, bytes):
                # The browser's harmless qSupported distinguishes this helper from a
                # byte-only GDB relay. No target connection or implicit halt is performed.
                if message == b"$qSupported#37":
                    await ws.send(b"+$PacketSize=10000#21")
                elif message != b"+":
                    raise ValueError("Use the advertised gnwmanager backend extension")
                continue
            request = json.loads(message)
            request_id = request.get("id")
            try:
                result = await loop.run_in_executor(
                    executor,
                    session.execute,
                    request["method"],
                    request.get("args", []),
                )
                response = {"id": request_id, "result": result}
            except Exception as error:
                LOG.debug("Backend operation failed", exc_info=True)
                response = {
                    "id": request_id,
                    "error": str(error) or type(error).__name__,
                }
            await ws.send(json.dumps(response))
    finally:
        await loop.run_in_executor(executor, session.close)
        executor.shutdown(wait=False)


async def serve_backend(
    factory,
    *,
    bind="127.0.0.1",
    port=8765,
    frequency=None,
    backend_name="openocd",
    cert=None,
    key=None,
    origins=None,
):
    active = False

    async def handle(ws):
        nonlocal active
        if ws.request.path != "/gdb":
            await ws.close(1008, "Unknown endpoint")
            return
        if active:
            await ws.close(1013, "Remote adapter already in use")
            return
        active = True
        try:
            await handle_session(ws, factory, frequency, backend_name)
        except Exception:
            LOG.warning("Remote adapter session ended", exc_info=True)
            await ws.close(1011, "Remote adapter backend unavailable")
        finally:
            active = False

    tls = None
    if cert:
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(cert, key)
    async with serve(
        handle,
        bind,
        port,
        ssl=tls,
        max_size=MAX_MEMORY * 2 + 1024,
        origins=origins or None,
        compression=None,
        ping_interval=20,
        ping_timeout=20,
    ):
        LOG.info("Listening at %s://%s:%s/gdb", "wss" if tls else "ws", bind, port)
        await asyncio.Future()
