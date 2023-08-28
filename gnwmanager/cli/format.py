from littlefs import LittleFSError
from typer import Option
from typing_extensions import Annotated

from gnwmanager.cli._parsers import int_parser
from gnwmanager.filesystem import get_flash_params


def _infer_block_count(gnw, offset):
    fs = gnw.filesystem(offset=offset, block_count=0, mount=False)
    try:
        fs.mount()
    except LittleFSError as e:
        raise ValueError("Unable to infer filesystem size. Please specify --size.") from e

    return fs.fs_stat().block_count


def format(
    size: Annotated[
        int,
        Option(
            min=0,
            parser=int_parser,
            help="Size of filesystem. Defaults to 0 (previous filesystem size).",
        ),
    ] = 0,
    offset: Annotated[
        int,
        Option(
            min=0,
            parser=int_parser,
            help="Distance in bytes from the END of the filesystem, to the END of flash.",
        ),
    ] = 0,
):
    """Format device's filesystem."""
    from .main import gnw

    flash_size, block_size = get_flash_params(gnw)

    if size > flash_size:
        raise ValueError(f"--size must be <= detected flash size {flash_size}.")
    if size % block_size != 0:
        raise ValueError(f"--size must be a multiple of block_size {block_size}.")
    if offset % block_size != 0:
        raise ValueError(f"--offset must be a multiple of block_size {block_size}.")

    block_count = int(size / block_size)

    if block_count == 0:
        # Attempt to infer block_count from a previous filesystem.
        block_count = _infer_block_count(gnw, offset)

    if block_count < 2:  # Even a block_count of 2 would be silly
        raise ValueError("Too few block_count.")

    fs = gnw.filesystem(offset=offset, block_count=block_count, mount=False)
    fs.format()
