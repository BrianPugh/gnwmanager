import os
import socket
import subprocess
from time import sleep
from typing import Generator, List

from gnwmanager.ocdbackend.base import OCDBackend

_COMMAND_TOKEN_STR = "\x1a"
_COMMAND_TOKEN_BYTES = _COMMAND_TOKEN_STR.encode("utf-8")
_BUFFER_SIZE = 4096


class OpenOCDAutoDetectError(Exception):
    """Was unable to detect a debugging probe."""


def _openocd_launch_commands(port: int) -> Generator[List[str], None, None]:
    openocd_executable = os.environ.get("OPENOCD", "openocd")
    base_cmd = [
        openocd_executable,
        "-c",
        f"tcl_port {port}",
    ]

    # STLink
    cmd = base_cmd.copy()
    cmd.extend(["-c", "source [find interface/stlink.cfg]"])
    cmd.extend(["-c", "adapter speed 500"])
    cmd.extend(["-c", "transport select hla_swd"])
    cmd.extend(["-c", "source [find target/stm32h7x.cfg]"])
    yield cmd

    # Raspberry Pi GPIO
    cmd = base_cmd.copy()
    cmd.extend(["-c", "source [find interface/sysfsgpio-raspberrypi.cfg]"])
    cmd.extend(["-c", "source [find openocd/rpi.cfg]"])
    cmd.extend(["-c", "transport select swd"])
    cmd.extend(["-c", "source [find target/stm32h7x.cfg]"])
    yield cmd

    # J-Link
    cmd = base_cmd.copy()
    cmd.extend(["-c", "source [find interface/jlink.cfg]"])
    cmd.extend(["-c", "adapter speed 500"])
    cmd.extend(["-c", "transport select swd"])
    cmd.extend(["-c", "source [find target/stm32h7x.cfg]"])
    yield cmd

    # CMSIS-DAP
    cmd = base_cmd.copy()
    cmd.extend(["-c", "source [find interface/cmsis-dap.cfg]"])
    cmd.extend(["-c", "adapter speed 500"])
    cmd.extend(["-c", "transport select swd"])
    cmd.extend(["-c", "source [find target/stm32h7x.cfg]"])
    yield cmd


def _launch_openocd(port: int) -> subprocess.Popen[bytes]:
    for cmd in _openocd_launch_commands(port):
        print(cmd)
        # TODO: swallow IO
        process = subprocess.Popen(cmd)
        sleep(0.3)
        if process.poll() is None:
            # Process is still running
            # it didn't immediately close due to not detecting probe.
            return process
    raise OpenOCDAutoDetectError


class OpenOCDBackend(OCDBackend):
    def __init__(self, connect_mode="attach", port=6666):
        super().__init__()
        self._address = ("localhost", port)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._openocd_process = None

    def open(self) -> OCDBackend:
        self._openocd_process = _launch_openocd(self._address[1])
        self._socket.connect(self._address)
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

    def __call__(self, cmd: str) -> bytes:
        """Invoke an OpenOCD command."""
        self._socket.send(cmd.encode("utf-8") + _COMMAND_TOKEN_BYTES)
        return self._receive_response()

    def _receive_response(self) -> bytes:
        responses = []

        while True:
            responses.append(self._socket.recv(_BUFFER_SIZE))

            if _COMMAND_TOKEN_BYTES in responses[-1]:
                # Strip trailing command token.
                responses[-1] = responses[-1][:-1]
                break

        return b"".join(responses)

    def read_memory(self, addr: int, size: int) -> bytes:
        """Reads a block of memory."""
        return self(f"read_memory 0x{addr:08X} 8 {size}")

    def write_memory(self, addr: int, data: bytes):
        """Writes a block of memory."""
        tcl_list = "{" + " ".join([hex(x) for x in data]) + "}"
        return self(f"write_memory 0x{addr:08X} 32 {tcl_list}")

    def read_register(self, name: str) -> int:
        """Read from a 32-bit core register."""
        raise NotImplementedError

    def write_register(self, name: str, val: int):
        """Write to a 32-bit core register."""
        return self(f"set {name.upper()} {val}")

    def set_frequency(self, freq: int):
        """Set probe frequency in hertz."""
        freq_khz = round(freq / 1000)
        self(f"adapter speed {freq_khz}")

    def reset(self):
        """Reset target."""
        self("reset run")

    def halt(self):
        """Halt target."""
        self("halt")

    def reset_and_halt(self):
        """Reset and halt target."""
        self("reset halt")

    def resume(self):
        """Resume target execution."""
        self("resume")

    def start_gdbserver(self, port, logging=True, blocking=True):
        """Start a blocking GDB Server."""
        raise NotImplementedError
