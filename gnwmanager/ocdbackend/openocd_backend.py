import logging
import os
import re
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from time import sleep, time
from typing import Generator, List, Tuple

from gnwmanager.exceptions import DataError, DebugProbeConnectionError, MissingThirdPartyError
from gnwmanager.ocdbackend.base import OCDBackend, TransferErrors
from gnwmanager.utils import kill_processes_by_name

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


def _openocd_launch_commands(port: int) -> Generator[Tuple[str, List[str]], None, None]:
    """Generate possible openocd launch commands for different debugging probes."""
    base_cmd = [
        str(find_openocd_executable()),
        "-c",
        f"tcl_port {port}",
    ]

    # STLink
    cmd = base_cmd.copy()
    cmd.extend(["-c", "adapter speed 4000"])
    cmd.extend(["-c", "source [find interface/stlink.cfg]"])
    cmd.extend(["-c", "transport select hla_swd"])
    cmd.extend(["-c", "source [find target/stm32h7x.cfg]"])
    yield "stlink", cmd

    # J-Link
    cmd = base_cmd.copy()
    cmd.extend(["-c", "adapter speed 4000"])
    cmd.extend(["-c", "source [find interface/jlink.cfg]"])
    cmd.extend(["-c", "transport select swd"])
    cmd.extend(["-c", "source [find target/stm32h7x.cfg]"])
    yield "jlink", cmd

    # CMSIS-DAP (pi pico)
    cmd = base_cmd.copy()
    cmd.extend(["-c", "adapter speed 4000"])
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

                if "Interface ready" in err:
                    raise OpenOCDAutoDetectError(f"Was able to connect to {name} probe, but unable to talk to device.")

                break
            elif _is_port_open(port):  # openocd is successfully running (but might actually still error out soon!)
                return process
            sleep(0.1)

    raise OpenOCDAutoDetectError("Unable to autodetect & connect to debugging probe.")


def _convert_hex_str_to_bytes(hex_str: bytes) -> bytes:
    try:
        return bytes(int(h, 16) for h in hex_str.decode().split())
    except ValueError:
        raise ValueError(f"Error decoding expected hex response: {hex_str}") from None


def find_openocd_executable() -> Path:
    openocd_executable = os.environ.get("OPENOCD", "openocd")
    if shutil.which(openocd_executable) is None:
        raise MissingThirdPartyError("Cannot find OpenOCD. Install via:\n    gnwmanager install openocd")
    return Path(openocd_executable)


def _get_openocd_version() -> Tuple[int, int, int]:
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
        self.version = _get_openocd_version()

    def open(self) -> OCDBackend:
        # In-case there's a previous openocd process still running.
        kill_processes_by_name("openocd")
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._openocd_process = _launch_openocd(self._address[1])
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
            self._openocd_process = None

    def __call__(self, cmd: str, *, decode=True) -> bytes:
        """Invoke an OpenOCD command."""
        try:
            self._socket.send(cmd.encode("utf-8") + _COMMAND_TOKEN_BYTES)
            return self._receive_response(decode=decode)
        except BrokenPipeError as e:
            assert self._openocd_process is not None
            _, err = self._openocd_process.communicate()
            err = err.decode()
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
        try:
            return int(res.split(": ")[-1], 16)
        except ValueError:
            raise DataError(f'Unable to parse read_uint32 response: "{res}"') from None

    def read_uint8(self, addr: int) -> int:
        res = self(f"mdb 0x{addr:08X}", decode=False).strip().decode()
        try:
            return int(res.split(": ")[-1], 16)
        except ValueError:
            raise DataError(f'Unable to parse read_uint32 response: "{res}"') from None

    def read_memory(self, addr: int, size: int) -> bytes:
        """Reads a block of memory."""
        if size <= 64:
            return bytearray(self.read_uint8(addr + offset) for offset in range(size))
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
