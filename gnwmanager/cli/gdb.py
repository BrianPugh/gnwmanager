import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional

from pyocd.gdbserver import GDBServer
from typer import Option
from typing_extensions import Annotated

from gnwmanager.utils import find_elf


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
    from .main import gnw

    if elf is None:
        elf = find_elf()

    gdb = GDBServer(gnw, core=0)
    gnw.gdbservers[0] = gdb
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
