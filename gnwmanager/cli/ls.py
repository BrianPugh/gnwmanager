from datetime import datetime, timezone
from pathlib import Path

from littlefs import LittleFS, LittleFSError
from typer import Argument, Option
from typing_extensions import Annotated

from gnwmanager.filesystem import get_filesystem


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


def ls(
    path: Annotated[Path, Argument(help="On-device folder path to list. Defaults to root")] = Path(),
    offset: Annotated[int, Option(help="Distance in bytes from the END of the filesystem, to the END of flash.")] = 0,
):
    from .main import session

    target = session.target
    fs = get_filesystem(target, offset=offset)
    _ls(fs, path.as_posix())
