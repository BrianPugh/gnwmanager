from pathlib import Path

from gnwmanager.cli._parsers import GnWType, OffsetType
from gnwmanager.cli.main import app


@app.command
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
