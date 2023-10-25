from pathlib import Path
from time import sleep

from typer import Argument, Option
from typing_extensions import Annotated

from .unlock import DeviceModel, is_gnw_locked


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


def lock(
    backup_dir: Annotated[
        Path,
        Argument(
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
            help="Directory of backed up files.",
        ),
    ],
    interactive: Annotated[bool, Option(help="Display interactive prompts.")] = True,
):
    """Re-lock your device."""
    from .main import gnw

    if is_gnw_locked(gnw):
        print("Device already locked. Skipping. Completely power cycle your device.")
        gnw.backend.reset()
        return

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
