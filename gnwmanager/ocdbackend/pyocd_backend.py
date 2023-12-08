from contextlib import suppress
from time import sleep

from gnwmanager.ocdbackend.base import OCDBackend, TransferErrors

with suppress(ImportError):
    import pyocd
    from pyocd.core.exceptions import TransferFaultError, TransferTimeoutError

    TransferErrors.add(TransferFaultError)
    TransferErrors.add(TransferTimeoutError)


class PyOCDBackend(OCDBackend):
    def __init__(self, connect_mode="attach"):
        super().__init__()
        from pyocd.core.helpers import ConnectHelper
        from pyocd.target import TARGET

        options = {
            "connect_mode": connect_mode,
            "warning.cortex_m_default": False,
            "persist": True,
        }
        if "stm32h7b0xx" in TARGET:  # pyocd prior to v0.36.0 doesn't have this builtin.
            options["target_override"] = "STM32h7b0xx"
            options["jlink.device"] = "STM32H7B0VB"

        session = ConnectHelper.session_with_chosen_probe(options=options)
        assert session is not None
        self.session = session
        self._frequency_override = 0

        version = tuple(int(x) for x in pyocd.__version__.split("."))
        assert len(version) == 3
        self.version = version

    @property
    def target(self):
        target = self.session.target
        assert target is not None
        return target

    @property
    def probe(self):
        probe = self.session.probe
        assert probe is not None
        return probe

    def set_frequency(self, freq: int):
        self._frequency_override = freq
        self.probe.set_clock(freq)

    def _set_default_frequency(self):
        """Attempt to set a good default frequency based on detected probe."""
        name = self.probe.product_name

        lookup = {
            "Picoprobe (CMSIS-DAP)": 10_000_000,
            "STM32 STLink": 10_000_000,
            "CMSIS-DAP_LU": 500_000,
            "J-Link EDU": 15_000_000,
        }

        with suppress(KeyError):
            self.probe.set_clock(lookup[name])

    def open(self) -> OCDBackend:
        self.session.open()
        if self._frequency_override:
            self.set_frequency(self._frequency_override)
        else:
            self._set_default_frequency()
        return self

    def close(self):
        self.session.close()

    def read_memory(self, addr: int, size: int) -> bytes:
        return bytes(self.target.read_memory_block8(addr, size))

    def read_register(self, name: str) -> int:
        return int(self.target.read_core_register(name))

    def write_register(self, name: str, val: int):
        self.target.write_core_register(name, val)

    def write_memory(self, addr: int, data: bytes):
        self.target.write_memory_block8(addr, data)

    def reset(self):
        self.target.reset()

    def halt(self):
        self.target.halt()

    def reset_and_halt(self):
        self.target.reset_and_halt()

    def resume(self):
        self.target.resume()

    def start_gdbserver(self, port, logging=True, blocking=True):
        from pyocd.gdbserver import GDBServer
        from pyocd.utility.color_log import build_color_logger

        self.session.options.set("gdbserver_port", port)

        if logging:
            build_color_logger(level=1)

        gdb = GDBServer(self.session, core=0)
        self.session.gdbservers[0] = gdb
        gdb.start()

        if blocking:
            while gdb.is_alive():
                sleep(0.1)

    @property
    def probe_name(self) -> str:
        return self.probe.product_name
