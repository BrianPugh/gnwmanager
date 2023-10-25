import importlib.resources
from time import sleep, time

from ..time import timestamp_now


def start_gnwmanager(force=False):
    """Load the Manager firmware into device SRAM, and run it.

    Parameters
    ----------
    force: bool
        Force start manager. Normally manager will only launch on first
        ``start_gnwmanager`` invocation.
    """
    if start_gnwmanager.started and not force:
        return

    from .main import gnw

    gnw.backend.reset_and_halt()
    gnw.reset_context_counter()

    # TODO: this is deprecated, but the replacement was introduced in python3.9.
    # Migrate to ``as_file`` once python3.8 hits EOL.
    with importlib.resources.path("gnwmanager", "firmware.bin") as f:
        firmware = f.read_bytes()

    gnw.write_memory(0x240E_6800, firmware)  # See STM32H7B0VBTx_FLASH.ld

    gnw.write_uint32("status", 0)  # To be 100% sure there's nothing residual in RAM.
    gnw.write_uint32("status_override", 0)  # To be 100% sure there's nothing residual in RAM.

    msp = int.from_bytes(firmware[:4], byteorder="little")
    pc = int.from_bytes(firmware[4:8], byteorder="little")
    gnw.backend.write_register("msp", msp)
    gnw.backend.write_register("pc", pc)

    gnw.backend.resume()
    gnw.wait_for_idle()

    start_gnwmanager.started = True

    gnw.write_uint32("utc_timestamp", timestamp_now())


start_gnwmanager.started = False
