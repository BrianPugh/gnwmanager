import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

from littlefs import LittleFS
from littlefs.context import UserContext
from littlefs.errors import LittleFSError
from littlefs.lfs import LFSConfig

from gnwmanager.gnw import GnW, Partition
from gnwmanager.utils import sha256
from gnwmanager.validation import validate_extflash_offset
from gnwmanager.exceptions import TooManyLFSPartitionsFoundError

log = logging.getLogger(__name__)

_gnw_cache = {}


def _test_lfs_integrity(gnw: GnW, partition: Partition, max_nodes: int = 50) -> bool:
    """Safely test LittleFS structural integrity with a read-only mount and bounded walk.

    Parameters
    ----------
    gnw: GnW
        Game and Watch object.
    partition: Partition
        The partition candidate to test.
    max_nodes: int
        Maximum number of filesystem nodes to traverse before passing the integrity check.
        If a partition is corrupt, it usually fails during mount or within the first few nodes.

    Returns
    -------
    bool
        True if the filesystem appears intact, False if LFS_ERR_CORRUPT is encountered.
    """
    filesystem_end = partition.address + partition.size
    # Create a fresh cache specifically for this test so we don't pollute the main one
    test_cache = {}
    lfs_context = LfsDriverContext(gnw, filesystem_end, cache=test_cache, read_only=True)

    fs = LittleFS(
        lfs_context,
        block_size=gnw.external_flash_block_size,
        block_count=partition.size // gnw.external_flash_block_size,
        block_cycles=500,
        mount=False,
    )

    try:
        fs.mount()
    except LittleFSError as e:
        if e.code == LittleFSError.Error.LFS_ERR_CORRUPT:
            log.debug(f"Partition at 0x{partition.address:X} failed mount integrity check.")
            return False
        raise

    nodes_checked = 0
    try:
        for root, dirs, files in fs.walk("/"):
            for name in dirs + files:
                # Reading the stat forces LittleFS to traverse the node's metadata
                fs.stat((Path(root) / name).as_posix())
                nodes_checked += 1
                if nodes_checked >= max_nodes:
                    return True
    except LittleFSError as e:
        if e.code == LittleFSError.Error.LFS_ERR_CORRUPT:
            log.debug(f"Partition at 0x{partition.address:X} failed deep integrity check at node {nodes_checked}.")
            return False
        raise

    return True


class LfsDriverContext(UserContext):
    def __init__(self, gnw: GnW, filesystem_end: int, cache: Optional[dict] = None, read_only: bool = False) -> None:
        validate_extflash_offset(filesystem_end)

        self.gnw = gnw
        self.filesystem_end = filesystem_end
        self.cache = _gnw_cache if cache is None else cache
        self.read_only = read_only

    def read(self, cfg: LFSConfig, block: int, off: int, size: int) -> bytearray:
        try:
            return bytearray(self.cache[block][off : off + size])
        except KeyError:
            pass
        if not self.read_only:
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

        if not self.read_only:
            addr = self.filesystem_end - ((block + 1) * cfg.block_size) + off
            self.gnw.program(0, addr, data, erase=False)

        return 0

    def erase(self, cfg: LFSConfig, block: int) -> int:
        self.cache[block] = bytearray([0xFF] * cfg.block_size)
        if not self.read_only:
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
    if offset == 0:
        candidates = [p for p in gnw.scan_geometry() if p.type == "LittleFS"]
        valid_partitions = []
        if candidates:
            for p in candidates:
                if _test_lfs_integrity(gnw, p):
                    valid_partitions.append(p)

            if len(valid_partitions) > 1:
                raise TooManyLFSPartitionsFoundError(
                    "Multiple valid LittleFS partitions detected (likely from moving to an SD layout "
                    "without erasing flash). Please specify which one to use with --offset."
                )
            elif len(valid_partitions) == 1:
                filesystem_end = valid_partitions[0].address + valid_partitions[0].size

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
