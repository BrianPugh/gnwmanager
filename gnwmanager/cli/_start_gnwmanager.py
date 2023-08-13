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
    # TODO: this is deprecated, but the replacement was introduced in python3.9.
    # Migrate to ``as_file`` once python3.8 hits EOL.
    if start_gnwmanager.started and not force:
        return

    from .main import session

    target = session.target
    assert target is not None

    target.reset_and_halt()
    addr = 0x240E_9800
    with importlib.resources.path("gnwmanager", "firmware.bin") as f:
        firmware = f.read_bytes()
        target.write_memory_block8(addr, firmware)

    target.write_int("program_status", 0)
    target.write_int("program_chunk_idx", 1)  # Can be overwritten later
    target.write_int("program_chunk_count", 100)  # Can be overwritten later

    msp = int.from_bytes(firmware[:4], byteorder="little")
    pc = int.from_bytes(firmware[4:8], byteorder="little")
    target.write_core_register("msp", msp)
    target.write_core_register("pc", pc)

    target.resume()
    target.wait_for_idle()

    start_gnwmanager.started = True

    target.write_int("utc_timestamp", timestamp_now())


start_gnwmanager.started = False
