from datetime import datetime, timezone
from pathlib import Path

from littlefs import LittleFS, LittleFSError
from typer import Argument, Option
from typing_extensions import Annotated

from gnwmanager.cli._parsers import int_parser
from gnwmanager.filesystem import get_filesystem


def _tree(fs: LittleFS, path: str, depth: int, max_depth: int):
    try:
        elements = list(fs.scandir(path))
        for idx, element in enumerate(elements):
            if element.type == 1:
                typ = "FILE"
                color = "\033[0m"
            elif element.type == 2:
                typ = "DIR "
                color = "\033[94m"
            else:
                typ = "UKWN"
                color = "\033[0m"

            fullpath = f"{path}/{element.name}"
            try:
                time_val = int.from_bytes(fs.getattr(fullpath, "t"), byteorder="little")
                time_str = datetime.fromtimestamp(time_val, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            except LittleFSError:
                time_str = " " * 19

            indent = ""
            if depth > 0:
                indent = "│   " * (depth - 1)
                if idx == (len(elements) - 1):
                    indent += "└── "
                else:
                    indent += "├── "
            print(f"{indent}\033[90m[{element.size:7}B {typ} {time_str}] {color}{element.name}\033[0m")

            # Recursive call on subdirectory
            if element.type == 2 and depth < max_depth:
                _tree(fs, fullpath, depth+1, max_depth)
    except LittleFSError as e:
        if e.code != -2:
            raise
        print(f"ls {path}: No such directory")


def tree(
    path: Annotated[
        Path,
        Argument(
            help="On-device folder path to list. Defaults to root",
        ),
    ] = Path(),
    depth: Annotated[
        int,
        Option(
            min=0,
            parser=int_parser,
            help="Maximum depth of the directory tree.",
        ),
    ] = 2,
    offset: Annotated[
        int,
        Option(
            min=0,
            parser=int_parser,
            help="Distance in bytes from the END of the filesystem, to the END of flash.",
        ),
    ] = 0,
):
    """List contents of device directory and its descendants."""
    from .main import session

    target = session.target
    fs = get_filesystem(target, offset=offset)
    _tree(fs, path.as_posix(), 0, depth)
