import logging
from pathlib import Path

from cyclopts import Parameter, validators
from typing_extensions import Annotated

from gnwmanager.cli._parsers import GnWType, OffsetType, convert_location, validate_flash_range
from gnwmanager.cli.main import app

log = logging.getLogger(__name__)


@app.command(group="Storage")
def flash(
    location: Annotated[
        int,
        Parameter(
            validator=validate_flash_range,
            converter=convert_location,
        ),
    ],
    file: Annotated[Path, Parameter(validator=validators.Path(exists=True, dir_okay=False))],
    offset: OffsetType = 0,
    *,
    gnw: GnWType,
):
    """Flash firmware to device.

    Parameters
    ----------
    location: Union[int, Literal["bank1", "bank2", "ext"]]
        Either an absolute flash address (e.g. 0x08000000) or one of {bank1, bank2, ext}.
    file: Path
        Binary file to flash.
    offset: int
        Offset into flash.
    """
    gnw.start_gnwmanager()
    data = file.read_bytes()

    addr = location + offset

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

    log.info(f"Flashing {len(data)} bytes to {'bank ' + str(bank) if bank else 'ext'} with relative-offset {offset}.")
    gnw.flash(bank, offset, data, progress=progress)
