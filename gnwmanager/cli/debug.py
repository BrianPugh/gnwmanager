from pathlib import Path
from time import time

import typer
from typer import Option
from typing_extensions import Annotated

from gnwmanager.cli._parsers import int_parser
from gnwmanager.filesystem import get_filesystem
from gnwmanager.utils import convert_framebuffer

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    add_completion=False,
    help="GnWManager internal debugging tools",
)


@app.command()
def screenshot(
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
):
    """Get a screenshot of the gnwmanager app."""
    from .main import session

    target = session.target

    framebuffer = target.read_mem("framebuffer")
    img = convert_framebuffer(framebuffer)

    img.save(dst)


@app.command()
def pdb(
    offset: Annotated[
        int,
        Option(
            min=0,
            parser=int_parser,
            help="Distance in bytes from the END of the filesystem, to the END of flash.",
        ),
    ] = 0,
):
    """Drop into debugging with app launched."""
    from .main import session

    target = session.target
    get_filesystem(target, offset=offset)

    breakpoint()


@app.command()
def hash():
    """Evaluates on-device hashing performance."""
    from .main import session

    target = session.target
    flash_size = target.read_int("flash_size")

    empty = b"\x00" * 32
    t_start = time()
    device_hashes = target.read_hashes(0, flash_size)
    t_end = time()

    assert empty not in device_hashes

    t_delta = t_end - t_start
    print(f"Hashed {len(device_hashes)} bytes in {t_delta:.3f}s.")
