import logging
import sys
from pathlib import Path
from time import sleep
from typing import Optional

from gnwmanager.cli._parsers import GnWType
from gnwmanager.cli.main import app
from gnwmanager.elf import SymTab
from gnwmanager.ocdbackend import TransferErrors

log = logging.getLogger(__name__)


@app.command(group="Developer")
def monitor(
    elf: Optional[Path] = None,
    buffer: str = "logbuf",
    index: str = "log_idx",
    utf8: bool = False,
    *,
    gnw: GnWType,
):
    """Monitor the device's stdout logging buffer.

    Parameters
    ----------
    elf: Optional[Path]
        Project's ELF file. Defaults to searching "build/" directory.
    buffer: str
        Log buffer variable name.
    index: str
        Log buffer index variable name.
    utf8: bool
        Logs should be decoded as utf-8.
    """
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

        if utf8:
            try:
                # Decode as UTF-8
                return data.decode("utf-8")
            except UnicodeDecodeError:
                return data.decode("utf-8", errors="replace")
        else:
            return "".join(chr(x) for x in data)

    last_idx = 0
    while True:
        try:
            log_idx = gnw.read_uint32(logidx_addr)

            if log_idx > last_idx:
                # print the new data since last iteration
                logbuf_str = read_and_decode(logbuf_addr + last_idx, log_idx - last_idx)
                log.info(f"incoming: {logbuf_str}")
                sys.stdout.write(logbuf_str)
                sys.stdout.flush()
            elif log_idx > 0 and log_idx < last_idx:
                # Get new data from the end of the buffer until the first null byte
                logbuf_str = read_and_decode(logbuf_addr + last_idx, logbuf_size - last_idx)
                logbuf_str += read_and_decode(logbuf_addr, log_idx)
                sys.stdout.write(logbuf_str)
                sys.stdout.flush()

            last_idx = log_idx
        except tuple(TransferErrors) as e:
            log.debug(e)

        sleep(0.1)
