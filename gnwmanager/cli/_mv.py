from pathlib import Path

from gnwmanager.cli._parsers import GnWType, OffsetType
from gnwmanager.cli.main import app


@app.command
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
    fs = gnw.filesystem(offset=offset)
    fs.rename(src.as_posix(), dst.as_posix())
