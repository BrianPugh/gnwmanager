from pathlib import Path

from typer import Argument, Option
from typing_extensions import Annotated

from gnwmanager.cli._parsers import int_parser


def rm(
    path: Annotated[
        Path,
        Argument(
            help="File or directory to delete.",
        ),
    ],
    recursive: Annotated[
        bool,
        Option(
            "--recursive",
            "-r",
            help="If a folder is specified, recursively delete all contents.",
        ),
    ] = False,
    offset: Annotated[
        int,
        Option(
            min=0,
            parser=int_parser,
            help="Distance in bytes from the END of the filesystem, to the END of flash.",
        ),
    ] = 0,
):
    """Delete a file or directory."""
    from .main import gnw

    fs = gnw.filesystem(offset=offset)

    # TODO: waiting on upstream littlefs-python
    fs.remove(path, recursive=recursive)
