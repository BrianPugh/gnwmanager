from functools import lru_cache

from littlefs import LittleFS
from littlefs.lfs import LFSConfig

from gnwmanager.validation import validate_extflash_offset


class LfsDriverContext:
    def __init__(self, target, filesystem_end) -> None:
        validate_extflash_offset(filesystem_end)

        self.target = target
        self.filesystem_end = filesystem_end
        self.cache = {}

    def read(self, cfg: LFSConfig, block: int, off: int, size: int) -> bytes:
        try:
            return bytes(self.cache[block][off : off + size])
        except KeyError:
            pass
        self.target.wait_for_all_contexts_complete()  # if a prog/erase is being performed, chip is not in memory-mapped-mode
        addr = 0x9000_0000 + self.filesystem_end - ((block + 1) * cfg.block_size)
        self.cache[block] = bytearray(self.target.read_memory_block8(addr, size))
        return bytes(self.cache[block][off : off + size])

    def prog(self, cfg: LFSConfig, block: int, off: int, data: bytes) -> int:
        # Update the local block if it has previously been read
        try:
            barray = self.cache[block]
            barray[off : off + len(data)] = data
        except KeyError:
            pass

        addr = self.filesystem_end - ((block + 1) * cfg.block_size) + off
        self.target.prog(0, addr, data, erase=False)

        return 0

    def erase(self, cfg: "LFSConfig", block: int) -> int:
        self.cache[block] = bytearray([0xFF] * cfg.block_size)
        offset = self.filesystem_end - ((block + 1) * cfg.block_size)
        self.target.erase_ext(offset, cfg.block_size)
        return 0

    def sync(self, cfg: "LFSConfig") -> int:
        return 0


@lru_cache
def get_filesystem(target, offset: int = 0):
    """Get LittleFS filesystem handle.

    Parameters
    ----------
    target
    offset:int
        Distance in bytes from the END of the filesystem, to the END of flash.
        Defaults to 0.
    """
    flash_size = target.read_int("flash_size")
    block_size = target.read_int("min_erase_size")

    filesystem_end = flash_size - offset

    lfs_context = LfsDriverContext(target, filesystem_end)
    fs = LittleFS(
        lfs_context,
        block_size=block_size,
        block_count=0,  # Autodetect filesystem size
        block_cycles=500,
        mount=False,  # Separately mount to not trigger a format-on-corruption
    )
    fs.mount()
    return fs