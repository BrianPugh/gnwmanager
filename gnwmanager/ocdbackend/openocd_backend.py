import socket

from gnwmanager.ocdbackend.base import OCDBackend

_COMMAND_TOKEN_STR = "\x1a"
_COMMAND_TOKEN_BYTES = _COMMAND_TOKEN_STR.encode("utf-8")
_BUFFER_SIZE = 4096


class OpenOCDBackend(OCDBackend):
    def __init__(self, connect_mode="attach", host="localhost", port=6666):
        super().__init__()
        self._address = (host, port)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def open(self) -> OCDBackend:
        self._socket.connect(self._address)
        return self

    def close(self):
        try:
            self("exit")
        finally:
            self._socket.close()

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
        return self("read_memory 0x{addr:08X} {size} 1")

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
        raise NotImplementedError

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
