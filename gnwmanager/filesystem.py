from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

from littlefs import LittleFS
from littlefs.context import UserContext
from littlefs.errors import LittleFSError
from littlefs.lfs import LFSConfig

from gnwmanager.gnw import GnW
from gnwmanager.utils import sha256
from gnwmanager.validation import validate_extflash_offset

_gnw_cache = {}


class LfsDriverContext(UserContext):
    def __init__(self, gnw: GnW, filesystem_end: int, cache: Optional[Dict] = None) -> None:
        validate_extflash_offset(filesystem_end)

        self.gnw = gnw
        self.filesystem_end = filesystem_end
        self.cache = _gnw_cache if cache is None else cache

    def read(self, cfg: LFSConfig, block: int, off: int, size: int) -> bytearray:
        try:
            return bytearray(self.cache[block][off : off + size])
        except KeyError:
            pass
        self.gnw.wait_for_all_contexts_complete()  # if a prog/erase is being performed, chip is not in memory-mapped-mode
        addr = 0x9000_0000 + self.filesystem_end - ((block + 1) * cfg.block_size)
        self.cache[block] = bytearray(self.gnw.read_memory(addr, size))
        return bytearray(self.cache[block][off : off + size])

    def prog(self, cfg: LFSConfig, block: int, off: int, data: bytes) -> int:
        # Update the local block if it has previously been read
        try:
            barray = self.cache[block]
            barray[off : off + len(data)] = data
        except KeyError:
            pass

        addr = self.filesystem_end - ((block + 1) * cfg.block_size) + off
        self.gnw.program(0, addr, data, erase=False)

        return 0

    def erase(self, cfg: LFSConfig, block: int) -> int:
        self.cache[block] = bytearray([0xFF] * cfg.block_size)
        offset = self.filesystem_end - ((block + 1) * cfg.block_size)
        self.gnw.erase(0, offset, cfg.block_size)
        return 0

    def sync(self, cfg: LFSConfig) -> int:
        return 0


def get_filesystem(gnw: GnW, offset: int = 0, block_count=0, mount=True) -> LittleFS:
    """Get LittleFS filesystem handle.

    Parameters
    ----------
    gnw: GnW
        Game and Watch object.
    offset: int
        Distance in bytes from the END of the filesystem, to the END of flash.
        Defaults to 0.
    block_count: int
        Number of blocks in filesystem.
        Defaults to ``0`` (infer from existing filesystem).
    mount: bool
        Mount the filesystem.
    """
    filesystem_end = gnw.external_flash_size - offset
    lfs_context = LfsDriverContext(gnw, filesystem_end)

    fs = LittleFS(
        lfs_context,
        block_size=gnw.external_flash_block_size,
        block_count=block_count,
        block_cycles=500,
        mount=False,  # Separately mount to not trigger a format-on-corruption
    )
    if mount:
        fs.mount()
    return fs


def is_existing_gnw_dir(fs: LittleFS, path: Union[str, Path]) -> bool:
    """Checks if a directory exists on the GnW filesystem."""
    if isinstance(path, Path):
        path = path.as_posix()

    try:
        stat = fs.stat(path)
    except LittleFSError as e:
        if e.code == LittleFSError.Error.LFS_ERR_NOENT:
            return False
        raise
    return stat.type == 2


def gnw_sha256(fs: LittleFS, path: Union[str, Path]):
    """Compute locally the sha256 digest of a remote file."""
    if isinstance(path, Path):
        path = path.as_posix()

    try:
        with fs.open(path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        return bytes(32)
    except LittleFSError as e:
        if e.code == LittleFSError.Error.LFS_ERR_NOTDIR:
            return bytes(32)
        raise

    return sha256(data)
