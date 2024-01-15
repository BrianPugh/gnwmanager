import logging
from datetime import datetime, timezone
from pathlib import Path

from cyclopts import Parameter, validators
from littlefs import LittleFS
from littlefs.errors import LittleFSError
from typing_extensions import Annotated

from gnwmanager.cli._parsers import GnWType, OffsetType
from gnwmanager.cli.main import app
from gnwmanager.utils import Color, colored

log = logging.getLogger(__name__)


def _tree(fs: LittleFS, path: str, depth: int, max_depth: int, prefix: str = ""):
    try:
        if depth == 0:
            print(colored(Color.BLUE, path))

        elements = list(fs.scandir(path))
        for idx, element in enumerate(elements):
            color = Color.NONE
            if element.type == 1:
                typ = "FILE"
            elif element.type == 2:
                typ = "DIR "
                color = Color.BLUE
            else:
                typ = "UKWN"

            fullpath = f"{path}/{element.name}"
            try:
                time_val = int.from_bytes(fs.getattr(fullpath, "t"), byteorder="little")
                time_str = datetime.fromtimestamp(time_val, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            except LittleFSError:
                time_str = " " * 19

            is_last_element = idx == (len(elements) - 1)
            indent = prefix
            if is_last_element:
                indent += "└── "
            else:
                indent += "├── "
            metadata = colored(Color.BLACK, f"[{element.size:7}B {typ} {time_str}]")
            print(f"{indent}{metadata} {colored(color, element.name)}")

            # Recursive call on subdirectory
            if element.type == 2 and depth < max_depth:
                next_prefix = prefix + ("    " if is_last_element else "│   ")
                _tree(fs, fullpath, depth + 1, max_depth, next_prefix)
    except LittleFSError as e:
        if e.code != -2:
            raise
        print(f"ls {path}: No such directory")


@app.command(group="Filesystem")
def tree(
    path: Path = Path(),
    depth: Annotated[int, Parameter(validator=validators.Number(gte=0))] = 2,
    offset: OffsetType = 0,
    *,
    gnw: GnWType,
):
    """List contents of device directory and its descendants.

    Parameters
    ----------
    path
        On-device folder path to list. Defaults to root.
    depth
        Maximum depth of the directory tree.
    offset
        Distance in bytes from the END of the filesystem, to the END of flash.
    """
    gnw.start_gnwmanager()
    fs = gnw.filesystem(offset=offset)
    _tree(fs, path.as_posix(), 0, depth)


def _infer_block_count(gnw, offset):
    fs = gnw.filesystem(offset=offset, block_count=0, mount=False)
    try:
        fs.mount()
    except LittleFSError:
        return 0

    return fs.fs_stat().block_count


@app.command(group="Filesystem")
def format(
    size: OffsetType = 0,
    offset: OffsetType = 0,
    *,
    only_if_shrinking: Annotated[bool, Parameter(negative="")] = False,
    gnw: GnWType,
):
    """Format device's filesystem.

    Parameters
    ----------
    size
        Size of filesystem. Defaults to previous filesystem size.
    offset
        Distance in bytes from the END of the filesystem, to the END of flash.
    only_if_shrinking
        Only format the filesystem if it's going to be smaller than a (possibly) existing filesystem.
        If growing; data is retained.
        Useful for just making sure there is a valid FS on the device.
    """
    gnw.start_gnwmanager()
    if size > gnw.external_flash_size:
        raise ValueError(f"--size must be <= detected flash size {gnw.external_flash_size}.")
    if size % gnw.external_flash_block_size != 0:
        raise ValueError(f"--size must be a multiple of gnw.external_flash_block_size {gnw.external_flash_block_size}.")
    if offset % gnw.external_flash_block_size != 0:
        raise ValueError(
            f"--offset must be a multiple of gnw.external_flash_block_size {gnw.external_flash_block_size}."
        )

    block_size = gnw.external_flash_block_size
    block_count = int(size / block_size)

    existing_block_count = _infer_block_count(gnw, offset)

    if existing_block_count > 0:
        log.info(f"Previous filesystem had {existing_block_count} blocks.")
    else:
        log.info("Unable to infer previous filesystem size.")

    if only_if_shrinking and existing_block_count > 0:
        if existing_block_count == block_count:
            log.info("Existing filesystem same size; skipping formatting.")
            return
        elif block_count > existing_block_count:
            log.info(f"Growing filesystem {existing_block_count * block_size} -> {block_count * block_size}.")
            fs = gnw.filesystem(offset=offset, block_count=0, mount=False)
            fs.fs_grow(block_count)
            return

    if block_count == 0:
        if existing_block_count == 0:
            raise ValueError("Unable to infer filesystem size. Please specify --size.")
        block_count = existing_block_count

    if block_count < 2:  # Even a block_count of 2 would be silly
        raise ValueError("Too few block_count.")

    fs = gnw.filesystem(offset=offset, block_count=block_count, mount=False)
    log.info(f"Formatting filesystem {block_count=} {block_size=} {offset=}.")
    fs.format()


def _ls(fs: LittleFS, path: str):
    try:
        for element in fs.scandir(path):
            if element.type == 1:
                typ = "FILE"
            elif element.type == 2:
                typ = "DIR "
            else:
                typ = "UKWN"

            fullpath = f"{path}/{element.name}"
            try:
                time_val = int.from_bytes(fs.getattr(fullpath, "t"), byteorder="little")
                time_str = datetime.fromtimestamp(time_val, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            except LittleFSError:
                time_str = " " * 19

            print(f"{element.size:7}B {typ} {time_str} {element.name}")
    except LittleFSError as e:
        if e.code != -2:
            raise
        print(f"ls {path}: No such directory")


@app.command(group="Filesystem")
def ls(
    path: Path = Path(),
    offset: OffsetType = 0,
    *,
    gnw: GnWType,
):
    """List contents of device directory.

    Parameters
    ----------
    path: Path
        On-device folder path to list.
    offset: int
        Distance from the END of the filesystem, to the END of flash.
    """
    gnw.start_gnwmanager()
    fs = gnw.filesystem(offset=offset)
    _ls(fs, path.as_posix())


@app.command(group="Filesystem")
def mkdir(
    path: Path,
    offset: OffsetType = 0,
    *,
    gnw: GnWType,
):
    """Create a directory on device.

    Parameters
    ----------
    path
        Directory to create.
    offset
        Distance in bytes from the END of the filesystem, to the END of flash.
    """
    gnw.start_gnwmanager()
    fs = gnw.filesystem(offset=offset)
    fs.makedirs(path.as_posix(), exist_ok=True)


@app.command(group="Filesystem")
def mv(
    src: Path,
    dst: Path,
    offset: OffsetType = 0,
    *,
    gnw: GnWType,
):
    """Move/Rename a file or directory.

    Parameters
    ----------
    src:
        Source file or directory.
    dst:
        Destination file or directory.
    offset:
        Distance from the END of the filesystem, to the END of flash.
    """
    gnw.start_gnwmanager()
    fs = gnw.filesystem(offset=offset)
    fs.rename(src.as_posix(), dst.as_posix())


@app.command(group="Filesystem")
def rm(
    path: Path,
    offset: OffsetType = 0,
    *,
    recursive: Annotated[
        bool,
        Parameter(name=["--recursive", "-r"], negative=[]),
    ] = False,
    gnw: GnWType,
):
    """Delete a file or directory.

    Parameters
    ----------
    path: Path
        File or directory to delete.
    offset: int
        Distance from the END of the filesystem, to the END of flash.
    recursive:
        Recursively delete a file/directory.
    """
    gnw.start_gnwmanager()
    fs = gnw.filesystem(offset=offset)
    fs.remove(path.as_posix(), recursive=recursive)
