from typing import Literal

from gnwmanager.cli._parsers import GnWType
from gnwmanager.cli.main import app


@app.command
def erase(
    location: Literal["bank1", "bank2", "ext", "all"],
    *,
    gnw: GnWType,
):
    """Erase a section of flash.

    Parameters
    ----------
    location: Literal["bank1", "bank2", "ext", "all"]
        Section to erase.
    """
    gnw.start_gnwmanager()

    if location in ("ext", "all"):
        # Just setting an artibrarily long timeout
        # TODO: maybe add visualization callback
        gnw.erase(0, 0, 0, whole_chip=True, timeout=10_000)

    if location in ("bank1", "all"):
        gnw.erase(1, 0, 0, whole_chip=True)

    if location in ("bank2", "all"):
        gnw.erase(2, 0, 0, whole_chip=True)
