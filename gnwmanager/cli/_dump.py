import logging
from pathlib import Path
from typing import Literal

from cyclopts import Parameter
from tqdm import tqdm
from typing_extensions import Annotated

from gnwmanager.cli._parsers import GnWType, OffsetType, convert_location, validate_flash_range
from gnwmanager.cli.main import app

log = logging.getLogger(__name__)


@app.command(group="Storage")
def dump(
    location: Annotated[
        int,
        Parameter(
            validator=validate_flash_range,
            converter=convert_location,
        ),
    ],
    dst: Path = Path("dump.bin"),
    size: OffsetType = 0,
    *,
    offset: OffsetType = 0,
    gnw: GnWType,
):
    """Read/Dump a section of flash.

    Parameters
    ----------
    location: Union[int, Literal["bank1", "bank2", "ext"]]
        Either an absolute flash address (e.g. 0x08000000) or one of {bank1, bank2, ext}.
    dst: Path
        Binary file to write contents to.
    size: int
        Number of bytes to read. If 0, will read all remaining data t location.
    offset: int
        Offset into flash.
    """
    gnw.start_gnwmanager()
    addr = location + offset

    chunks = []
    if 0x0800_0000 <= addr <= (0x0800_0000 + (256 << 10)):
        if size == 0:
            size = 0x0804_0000 - addr
        chunks.append(gnw.read_memory(addr, size))
    elif 0x0810_0000 <= addr <= (0x0810_0000 + (256 << 10)):
        if size == 0:
            size = 0x0814_0000 - addr
        chunks.append(gnw.read_memory(addr, size))
    else:
        if size == 0:
            if addr >= 0x9000_0000:
                size = 0x9000_0000 + gnw.external_flash_size - addr
            else:
                raise ValueError("Must specify size if reading from RAM address.")

        chunk_size = 256 << 10
        for _ in tqdm(range(0, size, chunk_size)):
            chunk_size = min(chunk_size, size)
            chunks.append(gnw.read_memory(addr, chunk_size))
            addr += chunk_size
            size -= chunk_size

    data = b"".join(chunks)
    dst.parent.mkdir(exist_ok=True, parents=True)
    dst.write_bytes(data)
