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
from gnwmanager.gnw import GnW
from gnwmanager.ocdbackend import OCDBackend

with suppress(ImportError):
    # By importing, makes things like the arrow-keys work.
    import readline  # Not available on windows

app = App()


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


@app.command
def info(*, gnw: GnWType):
    """Displays environment & device info."""
    gnw.start_gnwmanager()
    _display("OCD Backend Version:", ".".join(str(x) for x in gnw.backend.version))
    _display("Debug Probe:", gnw.backend.probe_name)

    try:
        device = DeviceModel.autodetect(gnw)
    except AutodetectError:
        device = "unknown"

    _display("Detected Stock Firmware:", str(device).upper())

    _display("External Flash Size (MB):", str(gnw.external_flash_size / (1 << 20)))


@app.command
def shell(
    offset: OffsetType = 0,
    *,
    gnw: GnWType,
):
    """Launch an interactive shell to browse device filesystem.

    Parameters
    ----------
    offset
        Distance from the END of the filesystem, to the END of flash.
    """
    gnw.default_filesystem_offset = offset

    def dispatcher(command, bound):
        # ``command`` is always ``main`` since we used the meta-app.
        try:
            return command(*bound.args, **bound.kwargs, gnw=gnw)
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


@app.command
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


@app.meta.default
def main(
    *tokens: Annotated[str, Parameter(show=False)],
    backend: Annotated[Literal["openocd", "pyocd"], Parameter(name=["--backend", "-b"])] = "openocd",
    frequency: Annotated[Optional[int], Parameter(name=["--frequency", "-f"], converter=int_parser)] = None,
    gnw: Optional[GnWType] = None,
):
    """An All-in-One Game & Watch flasher, debugger, filemanager, and more.

    Parameters
    ----------
    backend
        Underlying on-chip-debugger backend to use.
    frequency
        Debug probe frequency. Defaults to a typically reasonable fast value.
    """
    delimiter = "--"
    groups = [list(group) for key, group in itertools.groupby(tokens, lambda x: x == delimiter) if not key]

    close_on_exit = gnw is None
    try:
        for group in groups:
            additional_kwargs = {}
            command, bound = app.parse_args(group)

            if command.__name__ == "info":
                # Special case: print some system information prior to attempting
                # to connect to debug probe and device.
                _display_host_info(backend)

            if "gnw" in inspect.signature(command).parameters:
                if gnw is None:
                    gnw = GnW(OCDBackend[backend]())
                    if frequency is not None:
                        gnw.backend.set_frequency(frequency)
                    gnw.backend.open()
                additional_kwargs["gnw"] = gnw

            command(*bound.args, **bound.kwargs, **additional_kwargs)
    except BrokenPipeError:
        rich.print("[red]Error communicating with device (BrokenPipeError). Is it ON and connected?[/red]")
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
