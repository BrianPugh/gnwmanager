from pathlib import Path

from cyclopts import Parameter
from typing_extensions import Annotated

from gnwmanager.cli._parsers import GnWType, OffsetType
from gnwmanager.cli.main import app


@app.command
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
