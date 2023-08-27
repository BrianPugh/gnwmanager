import os
import signal
import subprocess
import sys
from pathlib import Path
from time import time
from typing import Optional

import typer
from pyocd.gdbserver import GDBServer
from typer import Option
from typing_extensions import Annotated

from gnwmanager.cli._parsers import int_parser
from gnwmanager.filesystem import get_filesystem
from gnwmanager.utils import convert_framebuffer, find_elf

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    add_completion=False,
    help="GnWManager internal debugging tools",
)


@app.command()
def screenshot(
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
):
    """Get a screenshot of the gnwmanager app."""
    from .main import session

    target = session.target

    framebuffer = target.read_mem("framebuffer")
    img = convert_framebuffer(framebuffer)

    img.save(dst)


@app.command()
def pdb(
    offset: Annotated[
        int,
        Option(
            min=0,
            parser=int_parser,
            help="Distance in bytes from the END of the filesystem, to the END of flash.",
        ),
    ] = 0,
):
    """Drop into debugging with app launched."""
    from .main import session

    target = session.target
    get_filesystem(target, offset=offset)

    breakpoint()


@app.command()
def hash():
    """Evaluates on-device hashing performance."""
    from .main import session

    target = session.target
    flash_size = target.read_int("flash_size")

    empty = b"\x00" * 32
    t_start = time()
    device_hashes = target.read_hashes(0, flash_size)
    t_end = time()

    assert empty not in device_hashes

    t_delta = t_end - t_start
    kbs = len(device_hashes) * 256 / t_delta
    print(f"Hashed {len(device_hashes)} 256KB chunks in {t_delta:.3f}s ({kbs:.1f} KB/s).")


@app.command()
def gdb(
    elf: Annotated[
        Optional[Path],
        Option(
            help='Project\'s ELF file. Defaults to searching "build/" directory.',
        ),
    ] = None,
):
    """Launch a gdbserver and connect to it with gdb.

    Checks the environment variable ``GDB`` for gdb executable.
    Defaults to ``arm-none-eabi-gdb``.
    """
    from .main import session

    if elf is None:
        elf = find_elf()

    gdb = GDBServer(session, core=0)
    session.gdbservers[0] = gdb
    gdb.start()

    gdb_executable = os.environ.get("GDB", "arm-none-eabi-gdb")

    cmd = [gdb_executable, str(elf), "-ex", "target extended-remote :3333"]
    process = subprocess.Popen(
        cmd,
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
        preexec_fn=os.setsid,
    )

    def handle_signal(signum, frame):
        # Forward the signal to the subprocess
        if process.poll() is None:  # Check if process is still running
            process.send_signal(signum)

    # Set up signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    exit_code = process.wait()

    sys.exit(exit_code)
