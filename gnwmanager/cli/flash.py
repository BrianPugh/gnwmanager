from pathlib import Path

from typer import Argument, Option
from typing_extensions import Annotated

from gnwmanager.cli._parsers import int_parser


def flash(
    location: Annotated[
        str,
        Argument(help="Either an absolute flash address (e.g. 0x08000000) or one of {bank1, bank2, ext}"),
    ],
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
            parser=int_parser,
            help="Offset into flash.",
        ),
    ] = 0,
):
    """Flash firmware to device."""
    from .main import gnw

    data = file.read_bytes()

    try:
        addr = int(location, 0)
    except ValueError:
        if location == "bank1":
            addr = 0x0800_0000
        elif location == "bank2":
            addr = 0x0810_0000
        elif location == "ext":
            addr = 0x9000_0000
        else:
            raise ValueError(f'Unknown location "{location}"') from None

    addr += offset

    if 0x0800_0000 <= addr <= (0x0800_0000 + (256 << 10)):
        progress = False
        bank = 1
        offset = addr - 0x0800_0000
    elif 0x0810_0000 <= addr <= (0x0810_0000 + (256 << 10)):
        progress = False
        bank = 2
        offset = addr - 0x0810_0000
    elif addr >= 0x9000_0000:
        progress = True
        bank = 0
        offset = addr - 0x9000_0000
    else:
        raise ValueError("Unsupported destination address.")

    gnw.flash(bank, offset, data, progress=progress)
