import importlib.resources
import logging
from argparse import Namespace
from pathlib import Path
from typing import Annotated, Optional

from cyclopts import App, Group, Parameter, validators
from cyclopts.types import ExistingBinPath

from gnwmanager.cli._parsers import GnWType
from gnwmanager.cli.gnw_patch.exception import NotEnoughSpaceError
from gnwmanager.cli.gnw_patch.mario import MarioGnW
from gnwmanager.cli.gnw_patch.zelda import ZeldaGnW
from gnwmanager.cli.main import app

log = logging.getLogger(__name__)

app.command(flash_patch := App("flash-patch", help="Patch & flash nintendo firmware for dual-boot."))


def _log_patching_results(device, internal_remaining_free, compressed_memory_remaining_free):
    log.info("Binary Patching Complete!")
    log.info(f"    Internal Firmware Used:  {len(device.internal) - internal_remaining_free} bytes")
    log.info(f"        Free: {internal_remaining_free} bytes")
    log.info(f"    Compressed Memory Used: {len(device.compressed_memory) - compressed_memory_remaining_free} bytes")
    log.info(f"        Free: {compressed_memory_remaining_free} bytes")
    log.info(f"    External Firmware Used: {len(device.external)} bytes")


def _common_prepare(cls, internal: Path, external: Path, bootloader: bool):
    if bootloader:
        version = "0x08032000"
    else:
        version = "default"
    log.info(f"loading {version}.bin")
    patch_data = (
        importlib.resources.files(f"gnwmanager.cli.gnw_patch.binaries.{cls.name}") / f"{version}.bin"
    ).read_bytes()
    elf = importlib.resources.files(f"gnwmanager.cli.gnw_patch.binaries.{cls.name}") / f"{version}.elf"
    device = cls(internal, elf, external)
    device.crypt()  # Decrypt external firmware.

    # Copy over novel code.
    novel_code_start = device.internal.STOCK_ROM_END
    device.internal[novel_code_start:] = patch_data[novel_code_start:]
    if bootloader:
        # An additional 73728 Bytes.
        # leaves 200KB onward for the bootloader.
        device.internal.extend(b"\x00" * ((200 * (1 << 10)) - 0x20000))
    else:
        # An additional 128KB
        device.internal.extend(b"\x00" * 0x20000)

    return device


low_level_flash = Group("Low Level Flags")
high_level_flash = Group("High Level Flags", validator=validators.MutuallyExclusive())


@flash_patch.command(default_parameter=Parameter(negative=()))
def mario(
    internal: ExistingBinPath,
    external: ExistingBinPath,
    *,
    gnw: GnWType,
    bootloader: bool = False,
    disable_sleep: Annotated[bool, Parameter(group=low_level_flash)] = False,
    sleep_time: Annotated[Optional[int], Parameter(validator=validators.Number(gte=1, lte=1092))] = None,
    no_save: Annotated[bool, Parameter(group=low_level_flash)] = False,
    no_mario_song: Annotated[bool, Parameter(group=low_level_flash)] = False,
    no_sleep_images: Annotated[bool, Parameter(group=low_level_flash)] = False,
    no_smb2: Annotated[bool, Parameter(group=low_level_flash)] = False,
    slim: Annotated[bool, Parameter(group=high_level_flash)] = False,
    internal_only: Annotated[bool, Parameter(group=high_level_flash)] = False,
):
    """Patch & Flash original mario firmware.

    This is intended as a simplified way of patching firmware; customization is limited.

    For complete customization, goto the original repo:
        https://github.com/BrianPugh/game-and-watch-patch

    Parameters
    ----------
    internal: Path
        Path to internal flash dump from "gnwmanager dump".
        Usually "internal_flash_backup_mario.bin"
    external: Path
        Path to external flash dump from "gnwmanager dump".
        Usually "flash_backup_mario.bin"
    bootloader: bool
        Leave room and flash the sd-card bootloader.
        The LEFT+GAME combination will launch the sd-card bootloader at 0x08032000.
    disable_sleep: bool
        Disables sleep timer.
    sleep_time: int
        Go to sleep after this many seconds of inactivity.
    no_save: bool
        Don't use up 2 pages (8192 bytes) of extflash for non-volatile saves.
        High scores and brightness/volume configurations will NOT survive homebrew launches.
    no_mario_song: bool
        Remove the mario song easter egg to save space.
    no_sleep_images: bool
        Remove the 5 sleeping images to save space.
    no_smb2: bool
        Remove the super mario bro's 2 ROM.
    slim: bool
        Remove bulky easter eggs (mario song and sleeping images) from extflash.
    internal_only: bool
        Configuration so no external flash is used.
    """
    if internal_only:
        slim = True
        no_save = True
    if slim:
        no_mario_song = True
        no_sleep_images = True
    if internal_only and bootloader:
        log.warning("Removing SMB2 to make room for bootloader.")
        no_smb2 = True

    device = _common_prepare(MarioGnW, internal, external, bootloader)

    device.args = Namespace(  # pyright: ignore[reportAttributeAccessIssue]
        disable_sleep=disable_sleep,
        sleep_time=sleep_time,
        no_save=no_save,
        no_mario_song=no_mario_song,
        no_sleep_images=no_sleep_images,
        no_smb2=no_smb2,
        compression_ratio=1.4,
    )

    internal_remaining_free, compressed_memory_remaining_free = device()

    if internal_only and device.external:
        raise NotEnoughSpaceError("Wasn't able to completely relocate mario firmware to bank1.")

    _log_patching_results(device, internal_remaining_free, compressed_memory_remaining_free)

    gnw.start_gnwmanager()
    gnw.flash(1, 0, device.internal, progress=False)
    if device.external:
        gnw.flash(0, 0, device.external, progress=True)


@flash_patch.command(default_parameter=Parameter(negative=()))
def zelda(
    internal: ExistingBinPath,
    external: ExistingBinPath,
    *,
    gnw: GnWType,
    bootloader: bool = False,
    no_la: Annotated[bool, Parameter(group=low_level_flash)] = False,
    no_sleep_images: Annotated[bool, Parameter(group=low_level_flash)] = False,
    no_second_beep: Annotated[bool, Parameter(group=low_level_flash)] = False,
    no_hour_tune: Annotated[bool, Parameter(group=low_level_flash)] = False,
):
    """Patch & Flash original zelda firmware.

    This is intended as a simplified way of patching firmware; customization is limited.

    For complete customization, goto the original repo:
        https://github.com/BrianPugh/game-and-watch-patch

    Parameters
    ----------
    internal: Path
        Path to internal flash dump from "gnwmanager dump".
        Usually "internal_flash_backup_zelda.bin"
    external: Path
        Path to external flash dump from "gnwmanager dump".
        Usually "flash_backup_zelda.bin"
    bootloader: bool
        Leave room and flash the sd-card bootloader.
        The LEFT+GAME combination will launch the sd-card bootloader at 0x08032000.
    no_la: bool
        Remove Link's Awakening to save space.
    no_sleep_images: bool
        Remove the 5 sleeping images to save space.
    no_second_beep: bool
        Remove the second beep in TIME/CLOCK.
    no_hour_tune: bool
        Remove the hour tune in TIME/CLOCK.
    """
    device = _common_prepare(ZeldaGnW, internal, external, bootloader)

    device.args = Namespace(  # pyright: ignore[reportAttributeAccessIssue]
        no_la=no_la,
        no_sleep_images=no_sleep_images,
        no_second_beep=no_second_beep,
        no_hour_tune=no_hour_tune,
    )

    internal_remaining_free, compressed_memory_remaining_free = device()

    _log_patching_results(device, internal_remaining_free, compressed_memory_remaining_free)

    Path("internal-patched.bin").write_bytes(device.internal)
    Path("external-patched.bin").write_bytes(device.external)

    gnw.start_gnwmanager()
    gnw.flash(1, 0, device.internal, progress=False)
    if device.external:
        gnw.flash(0, 0, device.external, progress=True)
