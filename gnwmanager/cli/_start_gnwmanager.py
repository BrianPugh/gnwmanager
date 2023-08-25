import importlib.resources
from time import sleep, time

from ..time import timestamp_now
from gnwmanager.buildinfo import GIT_HASH, BUILD_TIME

GNWMANAGER_MAGIC = 0x476e575f   # "GnW_"

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

    with importlib.resources.path("gnwmanager", "firmware.bin") as f:
        firmware = f.read_bytes()
        target.reset_and_halt()

        # No need to program flashapp if it's already running the correct version
        magic = target.read_int('magic')
        git_hash = target.read_mem('git_hash')
        git_hash_str = git_hash.decode("utf-8", "ignore").split('\0')[0]
        build_time = target.read_int("build_time")
        if magic == GNWMANAGER_MAGIC and git_hash_str == GIT_HASH and build_time == BUILD_TIME:
            print('gnwmanager already running on the target, no need to flash again.')
        else:
            addr = 0x240E_6800
            target.write_memory_block8(addr, firmware)

        target.write_int("status", 0)  # To be 100% sure there's nothing residual in RAM.
        target.write_int("status_override", 0)  # To be 100% sure there's nothing residual in RAM.

        msp = int.from_bytes(firmware[:4], byteorder="little")
        pc = int.from_bytes(firmware[4:8], byteorder="little")
        target.write_core_register("msp", msp)
        target.write_core_register("pc", pc)

        target.resume()
        target.wait_for_idle()

        start_gnwmanager.started = True

        target.write_int("utc_timestamp", timestamp_now())


start_gnwmanager.started = False
