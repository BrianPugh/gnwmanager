import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional

from typer import Option
from typing_extensions import Annotated

from gnwmanager.elf import find_elf


def gdb(
    elf: Annotated[
        Optional[Path],
        Option(
            show_default=False,
            help='Project\'s ELF file. Defaults to searching "build/" directory.',
        ),
    ] = None,
    port: Annotated[int, Option(help="GDB Server Port")] = 3333,
):
    """Launch a gdbserver and connect to it with gdb.

    Checks the environment variable ``GDB`` for gdb executable.
    Defaults to ``arm-none-eabi-gdb``.
    """
    from .main import gnw

    if elf is None:
        elf = find_elf()

    gdb_executable = os.environ.get("GDB", "arm-none-eabi-gdb")

    gnw.backend.start_gdbserver(port, logging=False, blocking=False)

    cmd = [gdb_executable, str(elf), "-ex", f"target extended-remote :{port}"]
    gdb_process = subprocess.Popen(
        cmd,
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
        preexec_fn=os.setsid,
    )

    def handle_signal(signum, frame):
        # Forward the signal to the subprocess
        if gdb_process.poll() is None:  # Check if process is still running
            gdb_process.send_signal(signum)

    # Set up signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    exit_code = gdb_process.wait()

    sys.exit(exit_code)
