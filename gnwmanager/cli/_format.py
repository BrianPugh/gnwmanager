from littlefs import LittleFSError

from gnwmanager.cli._parsers import GnWType, OffsetType
from gnwmanager.cli.main import app


def _infer_block_count(gnw, offset):
    fs = gnw.filesystem(offset=offset, block_count=0, mount=False)
    try:
        fs.mount()
    except LittleFSError as e:
        raise ValueError("Unable to infer filesystem size. Please specify --size.") from e

    return fs.fs_stat().block_count


@app.command
def format(
    size: OffsetType = 0,
    offset: OffsetType = 0,
    *,
    gnw: GnWType,
):
    """Format device's filesystem.

    Parameters
    ----------
    size
        Size of filesystem. Defaults to previous filesystem size.
    offset
        Distance in bytes from the END of the filesystem, to the END of flash.
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

    block_count = int(size / gnw.external_flash_block_size)

    if block_count == 0:
        # Attempt to infer block_count from a previous filesystem.
        block_count = _infer_block_count(gnw, offset)

    if block_count < 2:  # Even a block_count of 2 would be silly
        raise ValueError("Too few block_count.")

    fs = gnw.filesystem(offset=offset, block_count=block_count, mount=False)
    fs.format()
