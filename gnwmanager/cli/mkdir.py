from pathlib import Path

from typer import Argument, Option
from typing_extensions import Annotated

from gnwmanager.cli._parsers import int_parser
from gnwmanager.filesystem import get_filesystem


def mkdir(
    path: Annotated[
        Path,
        Argument(
            help="Directory to create.",
        ),
    ],
    offset: Annotated[
        int,
        Option(
            min=0,
            parser=int_parser,
            help="Distance in bytes from the END of the filesystem, to the END of flash.",
        ),
    ] = 0,
):
    """Create a directory on device."""
    from .main import gnw

    fs = gnw.filesystem(offset=offset)
    fs.makedirs(path.as_posix(), exist_ok=True)
