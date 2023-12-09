"""Unlock the factory Game & Watch device.

Based on:
    https://github.com/ghidraninja/game-and-watch-backup
"""

import importlib.resources
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from time import sleep
from typing import Literal, Optional, cast

from cyclopts import Parameter, validators
from typing_extensions import Annotated

from gnwmanager.cli._parsers import GnWType
from gnwmanager.cli.devices import DeviceModel
from gnwmanager.cli.main import app
from gnwmanager.ocdbackend import PyOCDBackend

_payload_flash_msg = """

Payload successfully flashed. Perform the following steps:

1. Fully remove power, then re-apply power.
2. Press the power button to turn on the device; the screen should turn blue.
"""


@contextmanager
def _message(msg: str):
    print(msg + "... ", end="", flush=True)
    try:
        yield
    finally:
        print("complete!")


model_literals = Literal["mario", "zelda"]


@app.command
def unlock(
    backup_dir: Annotated[Optional[Path], Parameter(validator=validators.Path(file_okay=False))] = None,
    model: Optional[model_literals] = None,
    *,
    gnw: GnWType,
):
    """Backs up and unlocks a stock Game & Watch console.

    Device must be *on* before running ``gnwmanager unlock``.

    Parameters
    ----------
    backup_dir: Optional[Path]
        Output directory for backed up files.
        Point to a previously interrupted ``unlock`` directory to resume.
        Defaults to creating a new backup directory.
    model: Optional[Literal["mario", "zelda"]]
        Game & Watch device firmware type.
        Defaults to autodetecting.
    """
    if isinstance(gnw.backend, PyOCDBackend):
        raise TypeError("Device unlocking requires using --backend=openocd")

    gnw.start_gnwmanager()

    if backup_dir is None:
        backup_dir = Path(f"backups-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}")
    backup_dir.mkdir(exist_ok=True)

    if model is None:
        # Try and detect model based on available files.
        # If resuming a previous interrupted unlocking procedure, on-device firmware may not be factory.
        backup_files = list(backup_dir.glob("itcm_backup_*.bin"))
        if len(backup_files) > 1:
            # Too many backup files; cannot interpret model type.
            raise ValueError("Too many backup files in provided directory.")
        elif len(backup_files) == 1:
            # Interpret model type from file
            model = cast(model_literals, backup_files[0].stem.split("_")[-1])
            device = DeviceModel[model](gnw)
        else:
            # No itcm backup found, attempt to autodetect based on on-device firmware.
            device = DeviceModel.autodetect(gnw)
            model = cast(model_literals, device)
    else:
        device = DeviceModel[model](gnw)

    assert model is not None

    # TODO: this is deprecated, but the replacement was introduced in python3.9.
    # Migrate to ``as_file`` once python3.8 hits EOL.
    with importlib.resources.path("gnwmanager", "unlock.bin") as f:
        unlock_firmware_data = f.read_bytes()

    print(f"\nIf interrupted, resume unlocking with:\n    gnwmanager unlock --backup-dir={backup_dir}\n")

    itcm = backup_dir / f"itcm_backup_{model}.bin"
    external_flash = backup_dir / f"flash_backup_{model}.bin"
    internal_flash = backup_dir / f"internal_flash_backup_{model}.bin"

    print(f"Detected {str(model).upper()} game and watch.")

    if itcm.exists():
        itcm_data = itcm.read_bytes()
        device.validate_itcm(itcm_data)
    else:
        with _message(f'Backing up itcm to "{itcm}"'):
            itcm_data = device.read_itcm()
            itcm.write_bytes(itcm_data)

    if external_flash.exists():
        external_flash_data = external_flash.read_bytes()
        device.validate_external_flash(external_flash_data)
    else:
        with _message(f'Backing up external flash to "{external_flash}"'):
            external_flash_data = device.read_external_flash()
            external_flash.write_bytes(external_flash_data)

    if internal_flash.exists():
        internal_flash_data = internal_flash.read_bytes()
        device.validate_internal_flash(internal_flash_data)
    else:
        payload = device.create_encrypted_payload(itcm_data, external_flash_data, unlock_firmware_data)

        with _message("Flashing payload to external flash"):
            gnw.flash(0, 0, payload)

        # Close connection in preparation for power removal
        gnw.backend.close()

        print(_payload_flash_msg)
        input('Press the "enter" key when the screen is blue: ')

        gnw.backend.open()
        gnw.backend.halt()

        with _message(f'Backing up internal flash to "{internal_flash}"'):
            internal_flash_data = device.read_internal_from_ram()
            internal_flash.write_bytes(internal_flash_data)

    with _message("Unlocking device"):
        gnw.backend.halt()
        gnw.write_uint32(0x52002008, 0x08192A3B)
        sleep(0.1)
        gnw.write_uint32(0x52002008, 0x4C5D6E7F)
        sleep(0.1)
        gnw.write_memory(0x52002021, b"\xAA")
        sleep(0.1)
        gnw.write_memory(0x52002018, b"\x02")
        sleep(0.2)

    with _message("Restoring firmware"):
        gnw.start_gnwmanager(force=True)
        gnw.flash(0, 0, external_flash_data)
        gnw.flash(1, 0, internal_flash_data)
        gnw.reset()

    print("Unlocking complete!")
    print("Pressing the power button should launch the original firmware.")
