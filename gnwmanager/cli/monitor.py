import sys
from contextlib import suppress
from pathlib import Path
from typing import Optional

from elftools.elf.elffile import ELFFile
from pyocd.core.exceptions import ProbeError, TransferFaultError, TransferTimeoutError
from typer import Option
from typing_extensions import Annotated

from gnwmanager.utils import find_elf


def monitor(
    elf: Annotated[
        Optional[Path], Option(help='Project\'s ELF file. Defaults to searching "build/" directory.')
    ] = None,
    buffer: Annotated[str, Option(help="Log buffer variable name.")] = "logbuf",
    index: Annotated[str, Option(help="Log buffer index variable name.")] = "log_idx",
):
    """Monitor the device's stdout logging buffer."""
    from .main import session

    if elf is None:
        elf = find_elf()

    with elf.open("rb") as f:
        elffile = ELFFile(f)
        symtab = elffile.get_section_by_name(".symtab")
        if symtab is None:
            raise ValueError("No symbol table found.")

        try:
            logbuf_sym = symtab.get_symbol_by_name(buffer)[0]
        except IndexError:
            raise ValueError(f'No buffer variable found "{buffer}".') from None

        logbuf_addr = logbuf_sym.entry.st_value
        logbuf_size = logbuf_sym.entry.st_size

        try:
            logidx_sym = symtab.get_symbol_by_name(index)[0]
        except IndexError:
            raise ValueError(f'No buffer index variable found "{index}".') from None

        logidx_addr = logidx_sym.entry.st_value

    target = session.target

    def read_and_decode(*args):
        data = target.read_memory_block8(*args)
        try:
            end = data.index(0)
            data = data[:end]
        except ValueError:
            pass

        return "".join(chr(x) for x in data)

    last_idx = 0
    while True:
        with suppress(TransferFaultError, TransferTimeoutError):
            log_idx = target.read_int(logidx_addr)

            if log_idx > last_idx:
                # print the new data since last iteration
                logbuf_str = read_and_decode(logbuf_addr + last_idx, log_idx - last_idx)
                sys.stdout.write(logbuf_str)
            elif log_idx > 0 and log_idx < last_idx:
                # Get new data from the end of the buffer until the first null byte
                logbuf_str = read_and_decode(logbuf_addr + last_idx, logbuf_size - last_idx)
                logbuf_str += read_and_decode(logbuf_addr, log_idx)
                sys.stdout.write(logbuf_str)

            last_idx = log_idx
