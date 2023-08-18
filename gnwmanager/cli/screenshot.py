from pathlib import Path

import tamp
from typer import Option
from typing_extensions import Annotated

from gnwmanager.cli._parsers import int_parser
from gnwmanager.filesystem import get_filesystem
from gnwmanager.utils import convert_framebuffer


def screenshot(
    src: Annotated[Path, Option()] = Path("/SCREENSHOT"),
    dst: Annotated[
        Path,
        Option(
            exists=False,
            file_okay=True,
            dir_okay=True,
            resolve_path=True,
            writable=True,
            help="Destination file or directory",
        ),
    ] = Path("screenshot.png"),
    offset: Annotated[
        int,
        Option(
            min=0,
            parser=int_parser,
            help="Distance in bytes from the END of the filesystem, to the END of flash.",
        ),
    ] = 0,
):
    """Pull and decode a screenshot from device."""
    from .main import session

    target = session.target
    fs = get_filesystem(target, offset=offset)

    with fs.open(src.as_posix(), "rb") as f:
        compressed_data = f.read()

    data = tamp.decompress(compressed_data)
    img = convert_framebuffer(data)
    img.save(dst)
