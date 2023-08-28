from pathlib import Path
from typing import Optional

import tamp
import typer
from elftools.elf.elffile import ELFFile
from typer import Option
from typing_extensions import Annotated

from gnwmanager.cli._parsers import int_parser
from gnwmanager.utils import convert_framebuffer, find_elf

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    add_completion=False,
    help="Capture and transfer screenshots from device.",
)


@app.command()
def capture(
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
    elf: Annotated[
        Optional[Path],
        Option(
            help='Project\'s ELF file. Defaults to searching "build/" directory.',
        ),
    ] = None,
    framebuffer: Annotated[
        str,
        Option(
            help="framebuffer variable name",
        ),
    ] = "framebuffer",
):
    """Capture a live screenshot from device's framebuffer."""
    from .main import gnw

    if elf is None:
        elf = find_elf()

    with elf.open("rb") as f:
        elffile = ELFFile(f)
        symtab = elffile.get_section_by_name(".symtab")
        if symtab is None:
            raise ValueError("No symbol table found.")

        try:
            framebuffer_sym = symtab.get_symbol_by_name(framebuffer)[0]
        except IndexError:
            raise ValueError(f'No framebuffer variable found "{framebuffer}".') from None

        framebuffer_addr = framebuffer_sym.entry.st_value
        framebuffer_size = framebuffer_sym.entry.st_size

    expected_framebuffer_size = 320 * 240 * 2
    if framebuffer_size != expected_framebuffer_size:
        raise ValueError(f"Unexpected framebuffer size {framebuffer_size}. Expected {expected_framebuffer_size}.")

    data = gnw.read_memory(framebuffer_addr, framebuffer_size)
    img = convert_framebuffer(data)
    img.save(dst)


@app.command()
def dump(
    src: Annotated[Path, Option()] = Path("/SCREENSHOT"),
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
    offset: Annotated[
        int,
        Option(
            min=0,
            parser=int_parser,
            help="Distance in bytes from the END of the filesystem, to the END of flash.",
        ),
    ] = 0,
):
    """Decode a saved screenshot from device filesystem."""
    from .main import gnw

    fs = gnw.filesystem(offset=offset)

    with fs.open(src.as_posix(), "rb") as f:
        compressed_data = f.read()

    data = tamp.decompress(compressed_data)
    img = convert_framebuffer(data)
    img.save(dst)
