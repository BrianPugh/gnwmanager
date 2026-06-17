import contextlib
import logging
import os
import re
import shutil
import socket
import subprocess
import tempfile
from collections import deque
from collections.abc import Generator
from pathlib import Path
from threading import Thread
from time import sleep, time
from typing import Deque, List, Tuple

from gnwmanager.exceptions import DataError, DebugProbeConnectionError, MissingThirdPartyError
from gnwmanager.ocdbackend.base import OCDBackend, TransferErrors
from gnwmanager.utils import env_is_yes_like, kill_processes_by_name

log = logging.getLogger(__name__)

_COMMAND_TOKEN_STR = "\x1a"
_COMMAND_TOKEN_BYTES = _COMMAND_TOKEN_STR.encode("utf-8")
_BUFFER_SIZE = 4096


class OpenOCDError(DebugProbeConnectionError):
    pass


class OpenOCDAutoDetectError(OpenOCDError):
    """Was unable to detect a debugging probe."""


TransferErrors.add(OpenOCDError)

_ramdisk = Path("/dev/shm")


def _drain_stderr(stream, buffer: "Deque[str]", level: int) -> None:
    """Continuously drain a subprocess stderr pipe.

    OpenOCD's stderr is a fixed-size OS pipe (~64 KB). If nothing reads it, the
    buffer eventually fills, OpenOCD's next write to stderr blocks, and it stops
    servicing the TCL command socket — wedging all transfers mid-session. This
    thread keeps the pipe drained at all times, retaining recent lines in
    ``buffer`` for later error reporting.
    """
    for line in iter(stream.readline, b""):
        text = line.decode(errors="replace").rstrip()
        if text:
            buffer.append(text)
            log.log(level, text)


def _pi_find_gpio_number(gpio_name):
    gpio_map = {}
    try:
        with Path("/sys/kernel/debug/gpio").open("r") as file:
            for line in file:
                parts = line.strip().split()
                if len(parts) == 3 and parts[0].startswith("gpio-"):
                    value_gpio_number = parts[0].split("-")[1]
                    key_gpio_name = parts[1].strip("()")
                    gpio_map[key_gpio_name] = value_gpio_number
    except Exception:
        return None

    return gpio_map.get(gpio_name)


def _openocd_launch_commands(port: int) -> Generator[tuple[str, list[str]], None, None]:
    """Generate possible openocd launch commands for different debugging probes."""
    base_cmd = [
        str(find_openocd_executable()),
        "-c",
        f"tcl_port {port}",
    ]

    # STLink — don't specify transport; the old "hla" driver auto-selects "hla_swd"
    # and the newer native "st-link" driver (OpenOCD post-Nov 2024) auto-selects "swd".
    cmd = base_cmd.copy()
    cmd.extend(["-c", "adapter speed 4000"])
    cmd.extend(["-c", "source [find interface/stlink.cfg]"])
    cmd.extend(["-c", "source [find target/stm32h7x.cfg]"])
    yield "stlink", cmd

    # J-Link
    cmd = base_cmd.copy()
    cmd.extend(["-c", "adapter speed 4000"])
    cmd.extend(["-c", "source [find interface/jlink.cfg]"])
    cmd.extend(["-c", "transport select swd"])
    cmd.extend(["-c", "source [find target/stm32h7x.cfg]"])
    yield "jlink", cmd

    # CMSIS-DAP (pi pico). Bit-banged SWD via RP2040 PIO with no level shifting;
    # signal integrity on hand-soldered G&W flying leads degrades quickly past
    # ~1 MHz and surfaces as BAD_HASH_RAM_COMPRESSED. 1 MHz is the safe default.
    cmd = base_cmd.copy()
    cmd.extend(["-c", "adapter speed 1000"])
    cmd.extend(["-c", "source [find interface/cmsis-dap.cfg]"])
    cmd.extend(["-c", "transport select swd"])
    cmd.extend(["-c", "source [find target/stm32h7x.cfg]"])
    yield "cmsis-dap", cmd

    # Raspberry Pi GPIO
    cmd = base_cmd.copy()
    cmd.extend(["-c", "adapter speed 1000"])
    cmd.extend(["-c", "source [find interface/sysfsgpio-raspberrypi.cfg]"])
    # SWCLK - GPIO25, physical pin 22
    # SWDIO - GPIO24, physical pin 18
    pi_sys_gpio24 = _pi_find_gpio_number("GPIO24")
    pi_sys_gpio25 = _pi_find_gpio_number("GPIO25")
    if pi_sys_gpio24 is not None and pi_sys_gpio25 is not None:
        cmd.extend(["-c", f"sysfsgpio_swd_nums {pi_sys_gpio25} {pi_sys_gpio24}"])
    else:
        cmd.extend(["-c", "sysfsgpio_swd_nums 25 24"])
    cmd.extend(["-c", "transport select swd"])
    cmd.extend(["-c", "source [find target/stm32h7x.cfg]"])
    yield "rpi-gpio", cmd


def _is_port_open(port, host="localhost", timeout=1) -> bool:
    """Check if a given port is open."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
        except Exception:
            return False
        return True


def _launch_openocd(port: int, timeout: float = 10.0):  # -> subprocess.Popen[bytes]:  # This type annotation is >=3.9
    for name, cmd in _openocd_launch_commands(port):
        log.info(f"Attempting to launch openocd: {' '.join(cmd)}")
        process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        deadline = time() + timeout
        while time() < deadline:
            if process.poll() is not None:  # openocd terminated, probe not detected
                _, err = process.communicate()
                err = err.decode()
                log.debug(err)

                # OpenOCD found and talked to the probe, but couldn't reach the target.
                # "Interface ready" is emitted by the plain SWD/JTAG (DAP) transports.
                # STLink uses the hla transport, which never prints "Interface ready" —
                # instead it reports its firmware/VID:PID, the measured target voltage,
                # and "init mode failed (unable to connect to the target)". Treat any of
                # these as "probe found, but device unreachable" so we don't fall through
                # to the misleading "couldn't find a probe" message.
                probe_found_markers = (
                    "Interface ready",
                    "Target voltage",
                    "init mode failed",
                    "unable to connect to the target",
                )
                if any(marker in err for marker in probe_found_markers):
                    raise OpenOCDAutoDetectError(
                        f"Was able to connect to {name} probe, but unable to talk to the device. "
                        "Try releasing the Game & Watch power button at the same time as running this command."
                    )

                break
            elif _is_port_open(port):  # openocd is successfully running (but might actually still error out soon!)
                sleep(0.5)
                if _is_port_open(port):
                    return process
            sleep(0.1)

    raise OpenOCDAutoDetectError("Unable to autodetect & connect to debugging probe.")


def _convert_hex_str_to_bytes(hex_str: bytes) -> bytes:
    try:
        return bytes(int(h, 16) for h in hex_str.decode().split())
    except ValueError:
        raise ValueError(f"Error decoding expected hex response: {hex_str}") from None


def _parse_md_response(res: str, addr: int, width: str) -> int:
    """Parse a `mdw`/`mdb` response, raising a helpful error if the target was lost."""
    if not res:
        raise OpenOCDError(
            f"OpenOCD lost contact with the target while reading 0x{addr:08X}. "
            "The CPU likely entered low-power/standby and could not be halted — "
            "try releasing the Game & Watch power button at the same time as running this command."
        )
    try:
        return int(res.split(": ")[-1], 16)
    except ValueError:
        raise DataError(f'Unable to parse read_{width} response: "{res}"') from None


def find_openocd_executable() -> Path:
    openocd_executable = os.environ.get("OPENOCD", "openocd")
    if shutil.which(openocd_executable) is None:
        raise MissingThirdPartyError("Cannot find OpenOCD. Install via:\n    gnwmanager install openocd")
    return Path(openocd_executable)


def _get_openocd_version() -> tuple[int, int, int]:
    # Run the command and capture the output
    openocd = find_openocd_executable()
    result = subprocess.run([openocd, "--version"], capture_output=True, text=True, check=True)
    # Use regular expression to find the version number
    match = re.search(r"(\d+\.\d+\.\d+)", result.stderr)
    if not match:
        raise ValueError("Unable to determine OpenOCD Version.")

    # Extract and parse the version number into a tuple
    version_str = match.group(1)
    version_tuple = tuple(int(x) for x in version_str.split("."))
    assert len(version_tuple) == 3

    return version_tuple


class OpenOCDBackend(OCDBackend):
    _socket: socket.socket

    def __init__(self, connect_mode="attach", port=6666):
        super().__init__()
        self._address = ("localhost", port)
        self._openocd_process = None
        self._stderr_buffer: Deque[str] = deque(maxlen=1000)
        self._stderr_thread = None
        self.version = _get_openocd_version()

    def open(self) -> OCDBackend:
        # In-case there's a previous openocd process still running.
        kill_processes_by_name("openocd")
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._openocd_process = _launch_openocd(self._address[1])

        # Always drain stderr, otherwise the OS pipe buffer fills and OpenOCD
        # deadlocks mid-session. GNWMANAGER_OPENOCD_DEBUG only controls whether
        # the drained lines are surfaced (INFO) or kept quiet (DEBUG).
        level = logging.INFO if env_is_yes_like("GNWMANAGER_OPENOCD_DEBUG") else logging.DEBUG
        self._stderr_thread = Thread(
            target=_drain_stderr,
            args=(self._openocd_process.stderr, self._stderr_buffer, level),
            daemon=True,
        )
        self._stderr_thread.start()

        for _ in range(5):
            try:
                self._socket.connect(self._address)
                break
            except (OSError, ConnectionRefusedError):
                sleep(0.5)

        return self

    def close(self):
        try:
            self("exit")
        finally:
            self._socket.close()
            if self._openocd_process and self._openocd_process.poll() is None:
                self._openocd_process.terminate()
                self._openocd_process.wait()
            if self._stderr_thread is not None:
                self._stderr_thread.join(timeout=2)
                self._stderr_thread = None
            self._openocd_process = None

    def _collect_stderr(self) -> str:
        """Wait for OpenOCD to exit and return its drained stderr output.

        Reads from the buffer filled by the background drain thread instead of
        calling ``process.communicate()`` (which would race with that thread for
        the pipe).
        """
        if self._openocd_process is not None:
            with contextlib.suppress(subprocess.TimeoutExpired):
                self._openocd_process.wait(timeout=2)
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=2)
        return "\n".join(self._stderr_buffer)

    def __call__(self, cmd: str, *, decode=True) -> bytes:
        """Invoke an OpenOCD command."""
        try:
            self._socket.send(cmd.encode("utf-8") + _COMMAND_TOKEN_BYTES)
            return self._receive_response(decode=decode)
        except (BrokenPipeError, ConnectionResetError) as e:
            assert self._openocd_process is not None
            err = self._collect_stderr()
            log.debug(err)
            if "Error connecting DP: cannot read IDR" in err:
                raise DebugProbeConnectionError(
                    "Was able to connect to debug probe, but unable to talk to device; may need to fully powercycle device"
                ) from e
            else:
                raise DebugProbeConnectionError from e

    def _receive_response(self, *, decode=True) -> bytes:
        responses = []

        while True:
            single_response = self._socket.recv(_BUFFER_SIZE)

            if single_response:
                responses.append(single_response)
            else:
                # An empty response means that the client has disconnected.
                response = b"".join(responses)
                raise DebugProbeConnectionError(f"Disconnected from openocd. Response so far: {response}")

            if _COMMAND_TOKEN_BYTES in responses[-1]:
                # Strip trailing command token.
                responses[-1] = responses[-1][:-1]
                break

        response = b"".join(responses)
        if decode:
            response = _convert_hex_str_to_bytes(response)
        return response

    def read_uint32(self, addr: int) -> int:
        """Reads a uint32 from addr."""
        res = self(f"mdw 0x{addr:08X}", decode=False).strip().decode()
        return _parse_md_response(res, addr, "uint32")

    def read_uint8(self, addr: int) -> int:
        res = self(f"mdb 0x{addr:08X}", decode=False).strip().decode()
        return _parse_md_response(res, addr, "uint8")

    def read_memory(self, addr: int, size: int) -> bytes:
        """Reads a block of memory."""
        if size <= 64:
            return bytes(self.read_uint8(addr + offset) for offset in range(size))
        else:
            with tempfile.TemporaryDirectory(dir=_ramdisk if _ramdisk.exists() else None) as temp_dir:
                temp_file = Path(temp_dir) / "scratch.bin"
                self(f"dump_image {temp_file.as_posix()} 0x{addr:08X} {size}", decode=False).decode()
                data = temp_file.read_bytes()
            if len(data) != size:
                raise OpenOCDError(f"Failed to read {size} bytes at 0x{addr:08X}. Received {len(data)} bytes.")

            return data

    def write_uint32(self, addr: int, val: int):
        """Writes a uint32 to addr."""
        self(f"mww 0x{addr:08x} 0x{val:08x}")

    def write_memory(self, addr: int, data: bytes):
        """Writes a block of memory."""
        if len(data) <= 64:
            for i, b in enumerate(data):
                self(f"mwb 0x{addr + i:08x} 0x{b:02X}")
        else:
            # For some reason, this doesn't handle small (single?) bytes well.
            with tempfile.TemporaryDirectory(dir=_ramdisk if _ramdisk.exists() else None) as temp_dir:
                temp_file = Path(temp_dir) / "scratch.bin"
                temp_file.write_bytes(data)
                self(f"load_image {temp_file.as_posix()} 0x{addr:08X} bin", decode=False).decode()

    def read_register(self, name: str) -> int:
        """Read from a 32-bit core register."""
        response = self(f"reg {name.lower()}", decode=False).decode()
        return int(response.split()[-1], 16)

    def write_register(self, name: str, val: int):
        """Write to a 32-bit core register."""
        self(f"reg {name.lower()} {val}", decode=False)

    def set_frequency(self, freq: int):
        """Set probe frequency in hertz."""
        freq_khz = round(freq / 1000)
        self(f"adapter speed {freq_khz}", decode=False)

    def reset(self):
        """Reset target."""
        self("reset run", decode=False)

    def halt(self):
        """Halt target."""
        self("halt", decode=False)

    def reset_and_halt(self):
        """Reset and halt target."""
        self("reset halt", decode=False)

    def resume(self):
        """Resume target execution."""
        self("resume", decode=False)

    def start_gdbserver(self, port, logging=True, blocking=True):
        """Start a blocking GDB Server."""
        # openocd already starts a gdb server
        if blocking:
            while True:
                sleep(1)

    @property
    def probe_name(self) -> str:
        return self("adapter name", decode=False).decode()
