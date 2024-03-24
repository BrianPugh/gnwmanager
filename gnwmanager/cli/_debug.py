import os
import signal
import subprocess
import sys
from pathlib import Path
from time import time
from typing import Optional

from cyclopts import App
from littlefs import LittleFSError

from gnwmanager.cli._parsers import GnWType, OffsetType
from gnwmanager.cli.main import app

app.command(debug := App(name="debug", group="Developer", help="GnWManager internal debugging tools."))


@debug.command
def pdb(
    offset: OffsetType = 0,
    *,
    gnw: GnWType,
    filesystem: bool = False,
):
    """Drop into debugging with app launched.

    Parameters
    ----------
    offset
        Distance from the END of the filesystem, to the END of flash.
    filesystem: bool
        Attempt to mount the filesystem.
    """
    gnw.start_gnwmanager()
    if filesystem:
        try:
            fs = gnw.filesystem(offset=offset)  # noqa: F841
        except LittleFSError as e:
            if e.code != LittleFSError.Error.LFS_ERR_CORRUPT:
                raise
            print("Unable to mount filesystem.")

    breakpoint()


@debug.command
def hash(
    *,
    gnw: GnWType,
):
    """Evaluates on-device hashing performance."""
    gnw.start_gnwmanager()

    flash_size = gnw.read_uint32("flash_size")

    t_start = time()
    device_hashes = gnw.read_hashes(0, flash_size)
    t_end = time()

    empty = b"\x00" * 32
    assert empty not in device_hashes

    t_delta = t_end - t_start
    kbs = len(device_hashes) * 256 / t_delta
    print(f"Hashed {len(device_hashes)} 256KB chunks in {t_delta:.3f}s ({kbs:.1f} KB/s).")


@debug.command
def gdb(
    elf: Optional[Path] = None,
    port: int = 3333,
    *,
    gnw: GnWType,
):
    """Launch halted gnwmanager, a gdbserver, and connect to it with gdb.

    Checks the environment variable ``GDB`` for gdb executable.
    Defaults to ``arm-none-eabi-gdb``.

    Parameters
    ----------
    elf: Optional[Path]
        Project's ELF file. Defaults to searching "build/" directory.
    port: int
        GDB Server Port.
    """
    if elf is None:
        elf = Path("build/gnwmanager.elf")

    gdb_executable = os.environ.get("GDB", "arm-none-eabi-gdb")

    gnw.start_gnwmanager(resume=False)
    gnw.backend.start_gdbserver(port, logging=False, blocking=False)

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
