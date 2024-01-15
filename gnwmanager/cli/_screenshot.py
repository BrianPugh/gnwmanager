import logging
from pathlib import Path
from typing import Optional

import tamp
from cyclopts import App

from gnwmanager.cli._parsers import GnWType, OffsetType
from gnwmanager.cli.main import app
from gnwmanager.elf import SymTab
from gnwmanager.utils import convert_framebuffer

log = logging.getLogger(__name__)

app.command(
    screenshot := App(
        name="screenshot",
        help="Capture and transfer screenshots from device.",
    )
)


@screenshot.command
def capture(
    dst: Path = Path("screenshot.png"),
    elf: Optional[Path] = None,
    framebuffer: str = "framebuffer",
    *,
    gnw: GnWType,
):
    """Capture a live screenshot from device's framebuffer.

    Parameters
    ----------
    dst: Path
        Destination file or directory.
    elf: Optional[Path]
        Project's ELF file. Defaults to searching "build/" directory.
    framebuffer: str
        Framebuffer variable name.
    """
    with SymTab(elf) if elf else SymTab.find() as symtab:
        framebuffer_sym = symtab[framebuffer]
        framebuffer_addr = framebuffer_sym.entry.st_value
        framebuffer_size = framebuffer_sym.entry.st_size
        log.debug(f'Using framebuffer variable "{framebuffer}" at 0x{framebuffer_addr:08X}.')

    expected_framebuffer_size = 320 * 240 * 2
    if framebuffer_size != expected_framebuffer_size:
        raise ValueError(f"Unexpected framebuffer size {framebuffer_size}. Expected {expected_framebuffer_size}.")

    data = gnw.read_memory(framebuffer_addr, framebuffer_size)
    img = convert_framebuffer(data)
    img.save(dst)


@screenshot.command
def dump(
    src: Path = Path("/SCREENSHOT"),
    dst: Path = Path("screenshot.png"),
    offset: OffsetType = 0,
    *,
    gnw: GnWType,
):
    """Decode a saved screenshot from device filesystem.

    GnWManager assumes the file represents a Tamp-compressed 320*240 RGB565 framebuffer.

    Parameters
    ----------
    src: Path
        Path to screenshot file.
    dst: Path
        Filename to save screenshot to.
    offset
        Distance in bytes from the END of the filesystem, to the END of flash.
    """
    gnw.start_gnwmanager()

    fs = gnw.filesystem(offset=offset)

    with fs.open(src.as_posix(), "rb") as f:
        compressed_data = f.read()
    log.info(f"Read {len(compressed_data)} bytes of tamp-compressed data.")

    data = tamp.decompress(compressed_data)
    log.info(f"Decompressed data to {len(data)} bytes.")
    img = convert_framebuffer(data)
    log.info(f"Saving screenshot dump to {dst}.")
    img.save(dst)
