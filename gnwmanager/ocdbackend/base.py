from abc import abstractmethod
from typing import Tuple

from autoregistry import Registry

TransferErrors = set()


class OCDBackend(Registry, suffix="Backend"):
    """Abstraction for handling lower level memory read/writes."""

    version: Tuple[int, int, int]

    def __init__(self):
        pass

    def __enter__(self) -> "OCDBackend":
        return self.open()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def open(self) -> "OCDBackend":
        """Open device connection."""
        return self

    def close(self):
        """Close device connection."""

    def read_uint32(self, addr: int):
        """Reads a uint32 from addr."""
        return int.from_bytes(self.read_memory(addr, 4), byteorder="little")

    def write_uint32(self, addr: int, val: int):
        """Writes a uint32 to addr."""
        return self.write_memory(addr, val.to_bytes(length=4, byteorder="little"))

    @abstractmethod
    def read_memory(self, addr: int, size: int) -> bytes:
        """Reads a block of memory."""
        raise NotImplementedError

    @abstractmethod
    def write_memory(self, addr: int, data: bytes):
        """Writes a block of memory."""
        raise NotImplementedError

    @abstractmethod
    def read_register(self, name: str) -> int:
        """Read from a 32-bit core register."""
        raise NotImplementedError

    @abstractmethod
    def write_register(self, name: str, val: int):
        """Write to a 32-bit core register."""
        raise NotImplementedError

    @abstractmethod
    def set_frequency(self, freq: int):
        """Set probe frequency in hertz."""
        raise NotImplementedError

    @abstractmethod
    def reset(self):
        """Reset target."""
        raise NotImplementedError

    @abstractmethod
    def halt(self):
        """Halt target."""
        raise NotImplementedError

    @abstractmethod
    def reset_and_halt(self):
        """Reset and halt target."""
        raise NotImplementedError

    @abstractmethod
    def resume(self):
        """Resume target execution."""
        raise NotImplementedError

    @abstractmethod
    def start_gdbserver(self, port, logging=True, blocking=True):
        """Start a blocking GDB Server."""
        raise NotImplementedError

    @property
    @abstractmethod
    def probe_name(self) -> str:
        raise NotImplementedError
