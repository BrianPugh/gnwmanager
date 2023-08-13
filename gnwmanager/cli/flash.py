from pathlib import Path

import typer
from pyocd.flash.file_programmer import FileProgrammer
from typer import Argument, Option
from typing_extensions import Annotated

from ._start_gnwmanager import start_gnwmanager

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False, add_completion=False)


@app.command()
def ext(
    file: Annotated[
        Path,
        Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            writable=False,
            readable=True,
            resolve_path=True,
            help="Binary file to flash.",
        ),
    ],
    offset: Annotated[
        int,
        Option(
            min=0,
        ),
    ] = 0,
):
    start_gnwmanager()
    breakpoint()
    raise NotImplementedError


@app.command()
def bank1(
    file: Annotated[
        Path,
        Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            writable=False,
            readable=True,
            resolve_path=True,
            help="Binary file to flash.",
        ),
    ],
    offset: Annotated[
        int,
        Option(
            min=0,
            max=256 << 10,
        ),
    ] = 0,
):
    from .main import session

    programmer = FileProgrammer(session, progress=None, no_reset=False)
    programmer.program(str(file), base_address=0x0800_0000 + offset)


@app.command()
def bank2(
    file: Annotated[
        Path,
        Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            writable=False,
            readable=True,
            resolve_path=True,
            help="Binary file to flash.",
        ),
    ],
    offset: Annotated[
        int,
        Option(
            min=0,
            max=256 << 10,
        ),
    ] = 0,
):
    from .main import session

    programmer = FileProgrammer(session, progress=None, no_reset=False)
    programmer.program(str(file), base_address=0x0810_0000 + offset)
