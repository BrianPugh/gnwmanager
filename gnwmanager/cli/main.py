import inspect
import itertools
import logging
import platform
import shutil
import subprocess
import sys
import traceback
from contextlib import suppress
from typing import Literal, Optional

import rich
from cyclopts import App, Parameter
from littlefs.errors import LittleFSError
from typing_extensions import Annotated

from gnwmanager import __version__
from gnwmanager.cli._parsers import GnWType, OffsetType, int_parser
from gnwmanager.cli.devices import AutodetectError, DeviceModel
from gnwmanager.exceptions import DataError, DebugProbeConnectionError
from gnwmanager.gnw import GnW
from gnwmanager.ocdbackend import OCDBackend

with suppress(ImportError):
    # By importing, makes things like the arrow-keys work.
    import readline  # Not available on windows

app = App(group_commands="Miscellaneous")

app.meta["--help"].group = "Admin"
app.meta["--version"].group = "Admin"


class ColorCodes:
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    RESET = "\033[0m"


class ColoredFormatter(logging.Formatter):
    LOG_COLORS = {
        "DEBUG": ColorCodes.BLUE,
        "INFO": ColorCodes.GREEN,
        "WARNING": ColorCodes.YELLOW,
        "ERROR": ColorCodes.RED,
        "CRITICAL": ColorCodes.MAGENTA,
    }

    def format(self, record):
        color = self.LOG_COLORS.get(record.levelname, ColorCodes.WHITE)
        record.msg = color + record.msg + ColorCodes.RESET
        return super().format(record)


def _display(field, value):
    print(f"{field:<28} {value}")


def _display_host_info(backend):
    """Display Host-side information.

    Useful for debugging
    """
    _display("Platform:", platform.platform(aliased=True))
    _display("Python Version:", sys.version)
    _display("GnWManager Executable:", shutil.which(sys.argv[0]))
    _display("GnWManager Version:", __version__)
    _display("OCD Backend:", backend)


@app.command(group="Admin")
def info(
    *,
    offset: OffsetType = 0,
    gnw: GnWType,
):
    """Displays environment & device info.

    Parameters
    ----------
    offset
        Distance in bytes from the END of the filesystem, to the END of flash.
    """
    gnw.start_gnwmanager()
    _display("OCD Backend Version:", ".".join(str(x) for x in gnw.backend.version))
    _display("Debug Probe:", gnw.backend.probe_name)

    try:
        device = DeviceModel.autodetect(gnw)
    except AutodetectError:
        device = "unknown"

    _display("Detected Stock Firmware:", str(device).upper())

    _display("External Flash Size (MB):", str(gnw.external_flash_size / (1 << 20)))
    _display("Locked?: ", "LOCKED" if gnw.is_locked() else "UNLOCKED")

    try:
        fs = gnw.filesystem(offset=offset, block_count=0)
    except LittleFSError as e:
        if e.code == LittleFSError.Error.LFS_ERR_CORRUPT:
            fs_size = "MISSING/CORRUPT"
        else:
            raise
    else:
        fs_stat = fs.fs_stat()
        fs_size_bytes = fs_stat.block_count * fs_stat.block_size
        fs_size = f"{fs_stat.block_size} * {fs_stat.block_count} ({fs_size_bytes})"

    _display("Filesystem Size (B):", fs_size)


@app.command()
def shell(
    offset: OffsetType = 0,
    *,
    gnw: GnWType,
):
    """Launch an interactive shell to run gnwmanager commands.

    Parameters
    ----------
    offset
        Distance from the END of the filesystem, to the END of flash.
    """
    gnw.default_filesystem_offset = offset

    def dispatcher(command, bound):
        # ``command`` is usually ``main`` since we used the meta-app.
        try:
            if command == main:
                return command(*bound.args, **bound.kwargs, gnw=gnw, exit_on_error=False)
            else:
                # Handles special cases like ``help``
                return command(*bound.args, **bound.kwargs)
        except LittleFSError as e:
            if e.code == LittleFSError.Error.LFS_ERR_CORRUPT:
                print("Missing or Corrupt filesystem; please format the filesystem.")
            else:
                print(traceback.format_exc())

    app.meta.interactive_shell(dispatcher=dispatcher, prompt="gnw$ ")


@app.command
def disable_debug(*, gnw: GnWType):
    """Disable the microcontroller's debug block."""
    gnw.write_uint32(0xE00E1004, 0x00000000)


@app.command(group="Admin")
def upgrade():
    """Update gnwmanager to latest stable version."""
    old_version = __version__
    subprocess.check_output([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_output([sys.executable, "-m", "pip", "install", "--upgrade", "gnwmanager"])
    res = subprocess.run([sys.executable, "-m", "gnwmanager", "--version"], stdout=subprocess.PIPE, check=True)
    new_version = res.stdout.decode().strip()
    if old_version == new_version:
        print(f"GnWManager up-to-date (v{new_version}).")
    else:
        print(f"GnWManager updated from v{old_version} to v{new_version}.")


@app.command(group="Admin", show=False)
def help(verbosity):
    """Display the help screen."""
    app.help_print([])


def _setup_logging(verbosity):
    formatter = ColoredFormatter("%(asctime)s - %(levelname)s: %(message)s")
    logging.basicConfig(stream=sys.stdout)
    logging.getLogger().setLevel(verbosity.upper())
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.handlers.clear()
    logger.addHandler(handler)


@app.meta.default
def main(
    *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
    backend: Annotated[Literal["openocd", "pyocd"], Parameter(name=["--backend", "-b"])] = "openocd",
    frequency: Annotated[Optional[int], Parameter(name=["--frequency", "-f"], converter=int_parser)] = None,
    verbosity: Annotated[
        Literal["debug", "info", "warning", "error"], Parameter(env_var="GNWMANAGER_VERBOSITY")
    ] = "warning",
    gnw: Optional[GnWType] = None,
    exit_on_error: Annotated[bool, Parameter(parse=False)] = True,
):
    """An All-in-One Game & Watch flasher, debugger, filemanager, and more.

    Parameters
    ----------
    backend
        Underlying on-chip-debugger backend to use.
    frequency
        Debug probe frequency. Defaults to a typically reasonable fast value.
    """
    _setup_logging(verbosity)

    delimiter = "--"
    groups = [list(group) for key, group in itertools.groupby(tokens, lambda x: x == delimiter) if not key] or [[]]

    close_on_exit = gnw is None
    try:
        for group in groups:
            additional_kwargs = {}
            command, bound = app.parse_args(group, exit_on_error=exit_on_error)

            if command.__name__ == "info":
                # Special case: print some system information prior to attempting
                # to connect to debug probe and device.
                _display_host_info(backend)

            if "gnw" in inspect.signature(command).parameters:
                if gnw is None:
                    gnw = GnW(OCDBackend[backend]())
                    gnw.backend.open()
                    if frequency is not None:
                        gnw.backend.set_frequency(frequency)
                additional_kwargs["gnw"] = gnw

            command(*bound.args, **bound.kwargs, **additional_kwargs)
    except DebugProbeConnectionError as e:
        rich.print(f"[red]Error communicating with device ({e}). Is it ON and connected?[/red]")
        close_on_exit = False
    except DataError as e:
        if e.args == ("BAD_FLASH_COMM",):
            rich.print("Failed to communicate with external flash chip. Check your soldering!")
        else:
            rich.print(f"Unexpected response from debug probe. {e}")
    except ConnectionResetError:
        print(traceback.format_exc())
        close_on_exit = False
    finally:
        if close_on_exit and gnw is not None:
            gnw.backend.close()


def run_app():
    # Suppresses log messages like:
    #    * "Invalid coresight component"
    #    * "Error attempting to probe CoreSight component referenced by ROM table entry #5"
    logging.getLogger("pyocd").setLevel(logging.CRITICAL)

    app.meta()
