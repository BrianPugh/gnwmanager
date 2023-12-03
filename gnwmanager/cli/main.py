import inspect
import itertools
import logging
import platform
import shutil
import sys
import traceback
from contextlib import suppress
from typing import Any, Dict, Literal, Optional

from cyclopts import App, Parameter
from littlefs import LittleFSError
from typing_extensions import Annotated

from gnwmanager import __version__
from gnwmanager.cli._parsers import GnWType, OffsetType, int_parser
from gnwmanager.gnw import GnW
from gnwmanager.ocdbackend import OCDBackend

with suppress(ImportError):
    # By importing, makes things like the arrow-keys work.
    import readline  # Not available on windows

app = App()


def _display_host_info(backend):
    """Display Host-side information.

    Useful for debugging
    """
    from gnwmanager.cli import _info

    _info.display("Platform:", platform.platform(aliased=True))
    _info.display("Python Version:", sys.version)
    _info.display("GnWManager Executable:", shutil.which(sys.argv[0]))
    _info.display("GnWManager Version:", __version__)
    _info.display("OCD Backend:", backend)


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


@app.meta.default
def main(
    *tokens: Annotated[str, Parameter(show=False)],
    backend: Annotated[Literal["openocd", "pyocd"], Parameter(name=["--backend", "-b"])] = "openocd",
    frequency: Annotated[
        Optional[int], Parameter(name=["--frequency", "-f"], converter=int_parser, show_default=False)
    ] = None,
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
    finally:
        if close_on_exit and gnw is not None:
            gnw.backend.close()


def run_app():
    # Suppresses log messages like:
    #    * "Invalid coresight component"
    #    * "Error attempting to probe CoreSight component referenced by ROM table entry #5"
    logging.getLogger("pyocd").setLevel(logging.CRITICAL)

    app.meta()
