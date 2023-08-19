from pathlib import Path

from typer import Argument, Option
from typing_extensions import Annotated

from gnwmanager.cli._parsers import int_parser
from gnwmanager.filesystem import get_filesystem


def mv(
    src: Annotated[
        Path,
        Argument(
            help="Source file or directory.",
        ),
    ],
    dst: Annotated[
        Path,
        Argument(
            help="Destination file or directory.",
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
    """Move/Rename a file or directory."""
    from .main import session

    target = session.target
    fs = get_filesystem(target, offset=offset)

    fs.rename(src.as_posix(), dst.as_posix())
