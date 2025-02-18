import importlib.resources
import logging
from argparse import Namespace
from typing import Annotated, Optional

from cyclopts import App, Group, Parameter, validators
from cyclopts.types import ExistingBinPath

from gnwmanager.cli._parsers import GnWType
from gnwmanager.cli.gnw_patch.mario import MarioGnW
from gnwmanager.cli.main import app

log = logging.getLogger(__name__)

app.command(flash_patch := App("flash-patch"))


def _read_patch(version: str = "default") -> tuple[bytes, bytes]:
    with importlib.resources.path("gnwmanager.cli.gnw_patch.binaries", f"{version}.bin") as f:
        firmware = f.read_bytes()

    with importlib.resources.path("gnwmanager.cli.gnw_patch.binaries", f"{version}.elf") as f:
        elf = f.read_bytes()

    return firmware, elf


low_level_flash = Group("Low level flash saving flags")
high_level_flash = Group("High level flash savings flags", validator=validators.MutuallyExclusive())


@flash_patch.command(default_parameter=Parameter(negative=()))
def mario(
    internal: ExistingBinPath,
    external: ExistingBinPath,
    *,
    gnw: GnWType,
    disable_sleep: Annotated[bool, Parameter(group=low_level_flash)] = False,
    sleep_time: Annotated[Optional[int], Parameter(validator=validators.Number(gte=1, lte=1))] = None,
    no_save: Annotated[bool, Parameter(group=low_level_flash)] = False,
    no_mario_song: Annotated[bool, Parameter(group=low_level_flash)] = False,
    no_sleep_images: Annotated[bool, Parameter(group=low_level_flash)] = False,
    slim: Annotated[bool, Parameter(group=high_level_flash)] = False,
    internal_only: Annotated[bool, Parameter(group=high_level_flash)] = False,
):
    """Patch & Flash original firmware.

    This is intended as a simplified way of patching firmware; customization is limited.

    For complete customization, goto the original repo:
        https://github.com/BrianPugh/game-and-watch-patch

    Parameters
    ----------
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
    slim: bool
        Remove mario song and sleeping images from extflash.
    internal_only: bool
        Configuration so no external flash is used.
    """
    if internal_only:
        slim = True
        no_save = True
    if slim:
        no_mario_song = True
        no_sleep_images = True

    version = "default"
    patch_data = (importlib.resources.files("gnwmanager.cli.gnw_patch.binaries") / f"{version}.bin").read_bytes()
    elf = importlib.resources.files("gnwmanager.cli.gnw_patch.binaries") / f"{version}.elf"

    device = MarioGnW(internal, elf, external)
    device.crypt()  # Decrypt external firmware.

    # Copy over novel code.
    novel_code_start = device.internal.STOCK_ROM_END
    device.internal[novel_code_start:] = patch_data[novel_code_start:]
    device.internal.extend(b"\x00" * 0x20000)  # TODO: might cause issues with bootloader.

    device.args = Namespace(  # pyright: ignore[reportAttributeAccessIssue]
        disable_sleep=disable_sleep,
        sleep_time=sleep_time,
        no_save=no_save,
        no_mario_song=no_mario_song,
        no_sleep_images=no_sleep_images,
        compression_ratio=1.4,
    )

    internal_remaining_free, compressed_memory_free = device()

    gnw.start_gnwmanager()
    gnw.flash(1, 0, device.internal, progress=False)
    if device.external:
        gnw.flash(0, 0, device.external, progress=True)
