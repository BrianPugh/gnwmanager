from cyclopts import Parameter
from typing_extensions import Annotated

from gnwmanager.cli._parsers import GnWType, convert_location
from gnwmanager.cli.main import app


def validate_internal_code(type_, value):
    if (0x0800_0000 <= value <= 0x0804_0000) or (0x0810_0000 <= value <= 0x0814_0000):
        return
    raise ValueError("Invalid start address.")


@app.command
def start(
    location: Annotated[
        int,
        Parameter(
            converter=convert_location,
            validator=validate_internal_code,
        ),
    ],
    offset: int = 0,
    *,
    halt: bool = False,
    gnw: GnWType,
):
    """Start firmware at location.

    Parameters
    ----------
    location: Union[int, Literal["bank1", "bank2"]]
        Either an absolute address (e.g. 0x08000000) or one of {bank1, bank2}.
    offset: int
        Offset into location.
    halt: bool
        Start in a halted state.
    """
    # Do NOT start gnwmanager
    addr = location + offset

    gnw.reset_and_halt()
    gnw.backend.write_register("msp", gnw.read_uint32(addr))
    gnw.backend.write_register("pc", gnw.read_uint32(addr + 4))

    if not halt:
        gnw.backend.resume()
