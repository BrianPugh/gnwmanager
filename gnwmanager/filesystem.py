from functools import lru_cache
from pathlib import Path
from typing import Tuple, Union

from littlefs import LittleFS, LittleFSError
from littlefs.lfs import LFSConfig

from gnwmanager.utils import sha256
from gnwmanager.validation import validate_extflash_offset

_gnw_cache = {}


class LfsDriverContext:
    def __init__(self, target, filesystem_end: int, cache: dict = None) -> None:
        validate_extflash_offset(filesystem_end)

        self.target = target
        self.filesystem_end = filesystem_end
        self.cache = _gnw_cache if cache is None else cache

    def read(self, cfg: LFSConfig, block: int, off: int, size: int) -> bytes:
        try:
            return bytes(self.cache[block][off : off + size])
        except KeyError:
            pass
        self.target.wait_for_all_contexts_complete()  # if a prog/erase is being performed, chip is not in memory-mapped-mode
        addr = 0x9000_0000 + self.filesystem_end - ((block + 1) * cfg.block_size)
        self.cache[block] = bytearray(self.target.read_mem(addr, size))
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
def get_flash_params(target) -> Tuple[int, int]:
    flash_size = target.read_int("flash_size")
    block_size = target.read_int("min_erase_size")

    return flash_size, block_size


def get_filesystem(target, offset: int = 0, block_count=0):
    """Get LittleFS filesystem handle.

    Parameters
    ----------
    target
    offset: int
        Distance in bytes from the END of the filesystem, to the END of flash.
        Defaults to 0.
    block_count: int
        Number of blocks in filesystem.
        Defaults to ``0`` (infer from existing filesystem).
    """
    flash_size, block_size = get_flash_params(target)
    filesystem_end = flash_size - offset
    lfs_context = LfsDriverContext(target, filesystem_end)

    fs = LittleFS(
        lfs_context,
        block_size=block_size,
        block_count=block_count,
        block_cycles=500,
        mount=False,  # Separately mount to not trigger a format-on-corruption
    )
    fs.mount()
    return fs


def is_existing_gnw_dir(fs: LittleFS, path: Union[str, Path]):
    if isinstance(path, Path):
        path = path.as_posix()

    try:
        stat = fs.stat(path)
    except LittleFSError as e:
        if e.code == -2:  # LFS_ERR_NOENT
            return False
        raise
    return stat.type == 2


def gnw_sha256(fs, path: Union[str, Path]):
    if isinstance(path, Path):
        path = path.as_posix()

    try:
        with fs.open(path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        return bytes(32)
    except LittleFSError as e:
        if e.code == -20:
            return bytes(32)
        raise

    return sha256(data)
