import sys
from contextlib import suppress
from pathlib import Path
from typing import Optional

from pyocd.core.exceptions import TransferFaultError, TransferTimeoutError
from typer import Option
from typing_extensions import Annotated

from gnwmanager.elf import SymTab


def monitor(
    elf: Annotated[
        Optional[Path], Option(help='Project\'s ELF file. Defaults to searching "build/" directory.')
    ] = None,
    buffer: Annotated[str, Option(help="Log buffer variable name.")] = "logbuf",
    index: Annotated[str, Option(help="Log buffer index variable name.")] = "log_idx",
):
    """Monitor the device's stdout logging buffer."""
    from .main import gnw

    with SymTab(elf) if elf else SymTab.find() as symtab:
        logbuf_sym = symtab[buffer]
        logbuf_addr = logbuf_sym.entry.st_value
        logbuf_size = logbuf_sym.entry.st_size

        logidx_sym = symtab[index]
        logidx_addr = logidx_sym.entry.st_value

    def read_and_decode(*args):
        data = gnw.read_memory(*args)
        try:
            end = data.index(0)
            data = data[:end]
        except ValueError:
            pass

        return "".join(chr(x) for x in data)

    last_idx = 0
    while True:
        with suppress(TransferFaultError, TransferTimeoutError):  # TODO: abstract this out to ocdbackend
            log_idx = gnw.read_uint32(logidx_addr)

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
