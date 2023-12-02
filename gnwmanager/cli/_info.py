from gnwmanager.cli._parsers import GnWType
from gnwmanager.cli.main import app
from gnwmanager.cli.unlock import AutodetectError, DeviceModel


def display(field, value):
    print(f"{field:<28} {value}")


@app.command
def info(*, gnw: GnWType):
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
