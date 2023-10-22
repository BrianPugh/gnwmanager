from contextlib import suppress
from time import sleep

from gnwmanager.ocdbackend.base import OCDBackend


class OpenOCDBackend(OCDBackend):
    def __init__(self, connect_mode="attach"):
        super().__init__()

    def read_memory(self, addr: int, size: int) -> bytes:
        """Reads a block of memory."""
        raise NotImplementedError

    def write_memory(self, addr: int, data: bytes):
        """Writes a block of memory."""
        raise NotImplementedError

    def read_register(self, name: str) -> int:
        """Read from a 32-bit core register."""
        raise NotImplementedError

    def write_register(self, name: str, val: int):
        """Write to a 32-bit core register."""
        raise NotImplementedError

    def set_frequency(self, freq: int):
        """Set probe frequency in hertz."""
        raise NotImplementedError

    def reset(self):
        """Reset target."""
        raise NotImplementedError

    def halt(self):
        """Halt target."""
        raise NotImplementedError

    def reset_and_halt(self):
        """Reset and halt target."""
        raise NotImplementedError

    def resume(self):
        """Resume target execution."""
        raise NotImplementedError

    def start_gdbserver(self, port, logging=True, blocking=True):
        """Start a blocking GDB Server."""
        raise NotImplementedError
