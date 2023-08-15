from enum import Enum

from pyocd.flash.eraser import FlashEraser
from typer import Argument
from typing_extensions import Annotated


class EraseLocation(str, Enum):
    bank1 = "bank1"
    bank2 = "bank2"
    ext = "ext"
    all = "all"


def erase(location: Annotated[EraseLocation, Argument(case_sensitive=False)]):
    from .main import session

    target = session.target

    location = location.value

    if location in ("ext", "all"):
        # Just setting an artibrarily long timeout
        # TODO: maybe add visualization callback
        target.erase_ext(0, 0, whole_chip=True, timeout=10_000)

    addresses = []
    if location in ("bank1", "all"):
        addresses.append((0x0800_0000, 0x0800_0000 + (256 * 1024)))
    if location in ("bank2", "all"):
        addresses.append((0x0810_0000, 0x0810_0000 + (256 * 1024)))

    if addresses:
        eraser = FlashEraser(session, FlashEraser.Mode.SECTOR)
        eraser.erase(addresses)
