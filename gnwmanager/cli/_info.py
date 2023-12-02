from cyclopts import Parameter
from typing_extensions import Annotated

from gnwmanager.gnw import GnW

from .main import app
from .unlock import AutodetectError, DeviceModel


def display(field, value):
    print(f"{field:<28} {value}")


@app.command
def info(*, gnw: Annotated[GnW, Parameter(parse=False)]):
    """Displays environment & device info."""
    # Note: part of this command exists in ``gnwmanager/cli/main.py``
    gnw.start_gnwmanager()
    display("Debug Probe:", gnw.backend.probe_name)

    try:
        device = DeviceModel.autodetect(gnw)
    except AutodetectError:
        device = "unknown"

    display("Detected Device:", str(device).upper())

    display("External Flash Size (MB):", str(gnw.external_flash_size / (1 << 20)))
