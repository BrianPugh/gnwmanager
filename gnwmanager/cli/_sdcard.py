import logging
from pathlib import Path
from typing import Annotated

from cyclopts import Group, Parameter, validators

from gnwmanager.cli._parsers import GnWType
from gnwmanager.cli.main import app

log = logging.getLogger(__name__)

group_sd = Group("SD Card (Only for game and watch with SD Card mod)")


@app.command(group=group_sd)
def sdls(
    path: str = "/",
    *,
    gnw: GnWType,
):
    """List files and directories on the SD card under ``path`` (directories end with ``/``)."""
    if not path.startswith("/"):
        raise ValueError("path shall start with '/'")
    gnw.start_gnwmanager()
    listing = gnw.sd_list_dir(path)
    # Plain print: Rich would interpret ``[...]`` in filenames (e.g. ``[!].bin``) as markup.
    print(listing, end="" if listing.endswith("\n") else "\n")


@app.command(group=group_sd)
def sdrm(
    path: str,
    *,
    gnw: GnWType,
):
    """Delete a file on the SD card."""
    if not path.startswith("/"):
        raise ValueError("path shall start with '/'")
    gnw.start_gnwmanager()
    gnw.sd_unlink(path)


@app.command(group=group_sd)
def sdpull(
    src_path: str,
    dest: Path,
    *,
    gnw: GnWType,
):
    """Copy a file from the SD card on the device to a path on this computer."""
    if not src_path.startswith("/"):
        raise ValueError("src_path shall start with '/'")
    if src_path.endswith("/"):
        raise ValueError("src_path shall be a file, not a directory")
    if dest.is_dir() or str(dest).endswith("/"):
        dest = dest / Path(src_path).name

    gnw.start_gnwmanager()
    data = gnw.sd_read_file(src_path, progress=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


@app.command(group=group_sd)
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
