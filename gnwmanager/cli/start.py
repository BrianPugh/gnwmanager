from enum import Enum

from typer import Argument, Option
from typing_extensions import Annotated


def start(
    location: Annotated[
        str,
        Argument(help="Either an absolute address (e.g. 0x08000000) or one of {bank1, bank2}"),
    ],
    offset: Annotated[
        int,
        Option(min=0, help="Offset into location."),
    ] = 0,
    halt: Annotated[
        bool,
        Option(help="Start in a halted state."),
    ] = False,
):
    """Start firmware at location."""
    from .main import gnw

    try:
        addr = int(location, 0)
    except ValueError:
        if location == "bank1":
            addr = 0x08000000
        elif location == "bank2":
            addr = 0x08100000
        else:
            raise ValueError(f'Unknown location "{location}"') from None

    addr += offset

    gnw.backend.reset_and_halt()
    gnw.backend.write_register("msp", gnw.read_uint32(addr))
    gnw.backend.write_register("pc", gnw.read_uint32(addr + 4))

    if not halt:
        gnw.backend.resume()
