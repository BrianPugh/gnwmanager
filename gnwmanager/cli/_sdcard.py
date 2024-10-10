import logging
from pathlib import Path

from cyclopts import Parameter, validators
from typing_extensions import Annotated

from gnwmanager.cli._parsers import GnWType
from gnwmanager.cli.main import app

log = logging.getLogger(__name__)


@app.command(group="SD Card (Only for game and watch with SD Card mod)")
def sdpush(
    file: Annotated[Path, Parameter(validator=validators.Path(exists=True, dir_okay=False))],
    dest_path: str,
    *,
    gnw: GnWType,
):
    """Store data in a file on SD Card of the game and watch.

    Parameters
    ----------
    destpath: str
        path of the file to create on the SD Card of the game and watch
    file: Path
        file to store in SD Card.
    """
    if not dest_path.startswith("/"):
        raise ValueError("dest_path shall start with '/'")
    if dest_path.endswith("/"):
        dest_path = f"{dest_path}{file.name}"

    gnw.start_gnwmanager()
    data = file.read_bytes()
    gnw.sd_write_file(dest_path, data, progress=True)
