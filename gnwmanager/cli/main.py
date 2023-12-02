import inspect
import itertools
import logging
import platform
import shutil
import sys
from typing import Literal, Optional

from cyclopts import App, Parameter
from typing_extensions import Annotated

from gnwmanager import __version__
from gnwmanager.cli._parsers import int_parser
from gnwmanager.gnw import GnW
from gnwmanager.ocdbackend import OCDBackend

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


@app.meta.default
def main(
    *tokens: Annotated[str, Parameter(show=False)],
    backend: Annotated[Literal["openocd", "pyocd"], Parameter(name=["--backend", "-b"])] = "openocd",
    frequency: Annotated[Optional[int], Parameter(name=["--frequency", "-f"], converter=int_parser)] = None,
):
    delimiter = "--"
    groups = [list(group) for key, group in itertools.groupby(tokens, lambda x: x == delimiter) if not key]

    gnw = None
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
        if gnw is not None:
            gnw.backend.close()


def run_app():
    # Suppresses log messages like:
    #    * "Invalid coresight component"
    #    * "Error attempting to probe CoreSight component referenced by ROM table entry #5"
    logging.getLogger("pyocd").setLevel(logging.CRITICAL)

    app.meta()
