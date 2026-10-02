import asyncio
import importlib
import json
from contextlib import asynccontextmanager
from unittest.mock import Mock

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from gnwmanager.server import BackendSession, handle_session, serve_backend


def backend():
    result = Mock()
    result.read_uint32.return_value = 0x12345678
    result.read_memory.side_effect = lambda addr, size: bytes(size)
    result.read_register.return_value = 42
    return result


def test_backend_delegation_and_reattach():
    first, second = backend(), backend()
    factory = Mock(side_effect=[first, second])
    session = BackendSession(factory, 1000000)
    assert session.execute("attach", [])
    first.open.assert_called_once()
    first.set_frequency.assert_called_once_with(1000000)
    assert session.execute("read_memory", [0x24000000, 4]) == "78563412"
    assert session.execute("read_memory", [1, 3]) == "000000"
    session.execute("write_memory", [0x24000000, "aabb"])
    first.write_memory.assert_called_once_with(0x24000000, b"\xaa\xbb")
    assert session.execute("read_register", ["pc"]) == 42
    session.execute("write_register", ["msp", 0x20020000])
    first.write_register.assert_called_once_with("msp", 0x20020000)
    first.halt.assert_not_called()
    first.resume.assert_not_called()
    assert session.execute("attach", [])
    first.close.assert_called_once()
    session.close()
    second.close.assert_called_once()


def test_aligned_register_writes_use_word_binding():
    target = backend()
    session = BackendSession(lambda: target)
    session.execute("attach", [])
    # DHCSR requires DBGKEY and C_HALT in the same 32-bit transaction.
    session.execute("write_memory", [0xE000EDF0, "03005fa0"])
    target.write_uint32.assert_called_once_with(0xE000EDF0, 0xA05F0003)
    target.write_memory.assert_not_called()
    session.close()


@pytest.mark.parametrize("addr,data", [(1, "03005fa0"), (0, "aabb"), (0, "0001020304050607")])
def test_other_memory_writes_keep_block_binding(addr, data):
    target = backend()
    session = BackendSession(lambda: target)
    session.execute("attach", [])
    session.execute("write_memory", [addr, data])
    target.write_memory.assert_called_once_with(addr, bytes.fromhex(data))
    target.write_uint32.assert_not_called()
    session.close()


@pytest.mark.parametrize(
    "method,args",
    [
        ("read_memory", [-1, 4]),
        ("read_memory", [0, 65537]),
        ("read_memory", [0xFFFFFFFF, 4]),
        ("write_register", ["pc", -1]),
        ("read_register", ["unknown"]),
        ("set_frequency", [0]),
        ("eval", []),
        ("attach", [1]),
        ("read_memory", []),
        ([], []),
    ],
)
def test_validation(method, args):
    session = BackendSession(backend)
    session.execute("attach", [])
    with pytest.raises(ValueError):
        session.execute(method, args)
    session.close()


def test_absent_target_retry_and_cleanup():
    missing, returned = backend(), backend()
    missing.open.side_effect = RuntimeError("target absent")
    missing._stderr_buffer = []
    session = BackendSession(Mock(side_effect=[missing, returned]))
    with pytest.raises(RuntimeError, match="No device detected"):
        session.execute("attach", [])
    assert session.backend is None
    missing.close.assert_called_once()
    assert session.execute("attach", [])
    session.close()


def test_real_websocket_frames_and_cleanup():
    async def scenario():
        target = backend()
        async with serve(lambda ws: handle_session(ws, lambda: target), "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            async with connect(f"ws://127.0.0.1:{port}/gdb") as ws:
                hello = json.loads(await ws.recv())
                assert hello["backend"] == "gnwmanager"
                assert hello["targetControl"] == "arm"
                target.open.assert_not_called()
                await ws.send(b"$qSupported#37")
                assert await ws.recv() == b"+$PacketSize=10000#21"
                await ws.send(b"+")
                for request_id, method, args in [
                    (1, "attach", []),
                    (2, "read_memory", [0, 4]),
                ]:
                    await ws.send(json.dumps({"id": request_id, "method": method, "args": args}))
                    reply = json.loads(await ws.recv())
                    assert reply == {
                        "id": request_id,
                        "result": True if request_id == 1 else "78563412",
                    }
        target.close.assert_called_once()
        target.halt.assert_not_called()
        target.resume.assert_not_called()

    asyncio.run(scenario())


def test_cli_passes_selected_backend_without_opening_it(monkeypatch):
    main = importlib.import_module("gnwmanager.cli.main")
    captured = {}

    async def run_server(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("gnwmanager.server.serve_backend", run_server)
    main.main("serve", "--port", "8766", backend="gdb", gdb_host="example", gdb_port=4321)
    assert captured["backend_name"] == "gdb"
    assert captured["port"] == 8766
    target = captured["factory"]()
    assert target.host == "example" and target.port == 4321
    assert target._socket is None


def test_rejects_second_browser_and_wrong_path(monkeypatch):
    async def scenario():
        target = backend()
        captured = []
        real_serve = serve

        @asynccontextmanager
        async def capture(handler, bind, port, **kwargs):
            async with real_serve(handler, bind, port, **kwargs) as server:
                captured.append(server)
                yield server

        monkeypatch.setattr("gnwmanager.server.serve", capture)
        task = asyncio.create_task(serve_backend(lambda: target, port=0))
        while not captured:
            await asyncio.sleep(0.01)
        port = captured[0].sockets[0].getsockname()[1]
        try:
            async with connect(f"ws://127.0.0.1:{port}/gdb") as first:
                await first.recv()
                async with connect(f"ws://127.0.0.1:{port}/gdb") as second:
                    with pytest.raises(ConnectionClosed) as exc:
                        await second.recv()
                    assert exc.value.rcvd.code == 1013
                async with connect(f"ws://127.0.0.1:{port}/wrong") as wrong:
                    with pytest.raises(ConnectionClosed) as exc:
                        await wrong.recv()
                    assert exc.value.rcvd.code == 1008
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(scenario())


@pytest.mark.parametrize("method", ["halt", "resume", "reset_and_halt"])
def test_target_control_delegates_to_existing_backend(method):
    target = backend()
    session = BackendSession(lambda: target)
    session.execute("attach", [])
    session.execute(method, [])
    getattr(target, method).assert_called_once_with()
    session.close()


@pytest.mark.parametrize("selected", ["openocd", "pyocd", "gdb"])
def test_server_uses_normal_backend_constructor_arguments(monkeypatch, selected):
    main = importlib.import_module("gnwmanager.cli.main")
    target = backend()
    constructor = Mock(return_value=target)
    monkeypatch.setattr(main, "OCDBackend", {selected: constructor})

    async def run_server(**kwargs):
        kwargs["factory"]()

    monkeypatch.setattr("gnwmanager.server.serve_backend", run_server)
    main.main("serve", backend=selected, gdb_host="example", gdb_port=4321)
    expected = {"host": "example", "port": 4321} if selected == "gdb" else {}
    constructor.assert_called_once_with(**expected)
    target.open.assert_not_called()
