from pathlib import Path
from time import sleep
from typing import Optional

from cyclopts import Parameter, validators
from typing_extensions import Annotated

from gnwmanager.cli._parsers import GnWType
from gnwmanager.cli.devices import DeviceModel
from gnwmanager.cli.main import app


class BadBackupError(Exception):
    """Bad backups detected."""


def _verify_backups(backup_dir) -> str:
    for model, device_model_cls in DeviceModel.items():
        itcm = backup_dir / f"itcm_backup_{model}.bin"
        external_flash = backup_dir / f"flash_backup_{model}.bin"
        internal_flash = backup_dir / f"internal_flash_backup_{model}.bin"

        if not (itcm.exists() and external_flash.exists() and internal_flash.exists()):
            continue

        device_model_cls.validate_itcm(itcm.read_bytes())
        device_model_cls.validate_external_flash(external_flash.read_bytes())
        device_model_cls.validate_internal_flash(internal_flash.read_bytes())

        # All files successfully validated
        return model

    raise BadBackupError


@app.command
def lock(
    backup_dir: Annotated[Optional[Path], Parameter(validator=validators.Path(exists=True, file_okay=False))] = None,
    *,
    skip_check: bool = False,
    interactive: bool = True,
    gnw: GnWType,
):
    """Re-lock your device.

    Parameters
    ----------
    backup_dir: Path
        Directory of backed up files.
    skip_check: bool
        Don't need to prove backed up files; skips check.
    interactive: bool
        Display interactive prompts.
    """
    if skip_check and backup_dir:
        raise ValueError("Only supply BACKUP_DIR or --skip-check.")

    gnw.start_gnwmanager()

    if gnw.is_locked():
        print("Device already locked. Skipping. Completely power cycle your device.")
        gnw.backend.reset()
        return

    if not skip_check:
        _verify_backups(backup_dir)

    if interactive:
        print("This will lock your device!")
        input('Press the "enter" key to continue: ')

    gnw.write_uint32(0x52002008, 0x08192A3B)
    sleep(0.1)
    gnw.write_uint32(0x52002008, 0x4C5D6E7F)
    sleep(0.1)
    gnw.write_memory(0x52002021, b"\x55")
    sleep(0.1)
    gnw.write_memory(0x52002018, b"\x02")
    sleep(0.1)

    gnw.backend.reset()

    print("Locking complete! Completely power cycle your device.")
