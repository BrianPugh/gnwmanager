from pathlib import Path

import typer
from typer import Option
from typing_extensions import Annotated

from gnwmanager.cli._parsers import int_parser
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
