from enum import Enum

from typer import Argument
from typing_extensions import Annotated


class EraseLocation(str, Enum):
    bank1 = "bank1"
    bank2 = "bank2"
    ext = "ext"
    all = "all"


def erase(
    location: Annotated[EraseLocation, Argument(case_sensitive=False, help="Section to erase.")],
):
    """Erase a section of flash."""
    from .main import gnw

    location_str = location.value

    if location_str in ("ext", "all"):
        # Just setting an artibrarily long timeout
        # TODO: maybe add visualization callback
        gnw.erase(0, 0, 0, whole_chip=True, timeout=10_000)

    if location_str in ("bank1", "all"):
        gnw.erase(1, 0, 0, whole_chip=True)

    if location_str in ("bank2", "all"):
        gnw.erase(2, 0, 0, whole_chip=True)
