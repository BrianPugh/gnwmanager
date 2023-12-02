from datetime import datetime, timezone
from pathlib import Path

from littlefs import LittleFS, LittleFSError

from gnwmanager.cli._parsers import GnWType, OffsetType
from gnwmanager.cli.main import app


def _ls(fs: LittleFS, path: str):
    try:
        for element in fs.scandir(path):
            if element.type == 1:
                typ = "FILE"
            elif element.type == 2:
                typ = "DIR "
            else:
                typ = "UKWN"

            fullpath = f"{path}/{element.name}"
            try:
                time_val = int.from_bytes(fs.getattr(fullpath, "t"), byteorder="little")
                time_str = datetime.fromtimestamp(time_val, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            except LittleFSError:
                time_str = " " * 19

            print(f"{element.size:7}B {typ} {time_str} {element.name}")
    except LittleFSError as e:
        if e.code != -2:
            raise
        print(f"ls {path}: No such directory")


@app.command
def ls(
    path: Path = Path(),
    offset: OffsetType = 0,
    *,
    gnw: GnWType,
):
    """List contents of device directory.

    Parameters
    ----------
    path: Path
        On-device folder path to list.
    offset: int
        Distance from the END of the filesystem, to the END of flash.
    """
    gnw.start_gnwmanager()
    fs = gnw.filesystem(offset=offset)
    _ls(fs, path.as_posix())
