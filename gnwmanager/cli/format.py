from typer import Option
from typing_extensions import Annotated

from gnwmanager.cli._parsers import int_parser
from gnwmanager.filesystem import get_filesystem, get_flash_params


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
    """Create a directory on device."""
    from .main import session

    target = session.target
    flash_size, block_size = get_flash_params(target)
    if offset % block_size != 0:
        raise ValueError(f"Size must be a multiple of {block_size}.")
    block_count = int(size / block_size)
    fs = get_filesystem(target, offset=offset, block_count=block_count)

    fs.format()
