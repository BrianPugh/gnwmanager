import importlib.resources
from datetime import datetime, timezone
from time import sleep, time


def timestamp_now() -> int:
    return int(round(datetime.now().replace(tzinfo=timezone.utc).timestamp()))


def read_int(key) -> int:
    from .main import Variable, comm, target

    if isinstance(key, str):
        addr = comm[key].address
    elif isinstance(key, Variable):
        addr = key.address
    elif isinstance(key, int):
        addr = key
    else:
        raise TypeError
    return target.read32(addr)


def write_int(key, val):
    from .main import Variable, comm, target

    if isinstance(key, str):
        addr = comm[key].address
    elif isinstance(key, Variable):
        addr = key.address
    elif isinstance(key, int):
        addr = key
    else:
        raise TypeError

    target.write32(addr, val)


_flashapp_status_enum_to_str = {
    0: "BOOTING",
    0xBAD00001: "BAD_HASH_RAM",
    0xBAD00002: "BAD_HAS_FLASH",
    0xBAD00003: "NOT_ALIGNED",
    0xCAFE0000: "IDLE",
    0xCAFE0001: "DONE",
    0xCAFE0002: "BUSY",
}
_flashapp_status_str_to_enum = {v: k for k, v in _flashapp_status_enum_to_str.items()}


class DataError(Exception):
    """Some data was not as expected."""


def wait_for_idle(timeout=10):
    """Block until the on-device status is matched."""
    time()
    t_deadline = time() + timeout
    error_mask = 0xFFFF_0000

    while True:
        status_enum = read_int("program_status")
        status_str = _flashapp_status_enum_to_str.get(status_enum, "UNKNOWN")
        if status_str == "IDLE":
            break
        elif (status_enum & error_mask) == 0xBAD0_0000:
            raise DataError(status_str)
        if time() > t_deadline:
            raise TimeoutError
        sleep(0.05)


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

    from .main import comm, target

    target.reset_and_halt()
    addr = 0x240E_9800
    with importlib.resources.path("gnwmanager", "firmware.bin") as f:
        firmware = f.read_bytes()
        target.write_memory_block8(addr, firmware)

    msp = int.from_bytes(firmware[:4], byteorder="little")
    pc = int.from_bytes(firmware[4:8], byteorder="little")

    write_int("program_status", 0)
    write_int("program_chunk_idx", 1)  # Can be overwritten later
    write_int("program_chunk_count", 100)  # Can be overwritten later

    target.write_core_register("msp", msp)
    target.write_core_register("pc", pc)

    target.resume()
    wait_for_idle()

    start_gnwmanager.started = True

    write_int("utc_timestamp", timestamp_now())


start_gnwmanager.started = False
