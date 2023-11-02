from .unlock import DeviceModel


def display(field, value):
    print(f"{field:<28} {value}")


def info():
    """Displays environment & device info.

    Note: part of this command exists in ``gnwmanager/cli/main.py``
    """
    from .main import gnw

    display("Debug Probe:", gnw.backend.probe_name)

    device = DeviceModel.autodetect(gnw)
    display("Detected Device:", str(device).upper())

    display("External Flash Size (MB):", str(gnw.external_flash_size / (1 << 20)))
