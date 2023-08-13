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
):
    from .main import session

    target = session.target

    try:
        addr = int(location, 0)
    except ValueError:
        if location == "bank1":
            addr = 0x08000000
        elif location == "bank2":
            addr = 0x08100000
        else:
            raise ValueError(f'Unknown location "{location}"') from None

    target.reset_and_halt()
    target.write_core_register("msp", target.read_int(addr))
    target.write_core_register("pc", target.read_int(addr + 4))
    target.resume()
