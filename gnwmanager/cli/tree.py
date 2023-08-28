from datetime import datetime, timezone
from pathlib import Path

from littlefs import LittleFS, LittleFSError
from typer import Argument, Option
from typing_extensions import Annotated

from gnwmanager.cli._parsers import int_parser
from gnwmanager.utils import Color, colored


def _tree(fs: LittleFS, path: str, depth: int, max_depth: int, prefix: str = ""):
    try:
        if depth == 0:
            print(colored(Color.BLUE, path))

        elements = list(fs.scandir(path))
        for idx, element in enumerate(elements):
            color = Color.NONE
            if element.type == 1:
                typ = "FILE"
            elif element.type == 2:
                typ = "DIR "
                color = Color.BLUE
            else:
                typ = "UKWN"

            fullpath = f"{path}/{element.name}"
            try:
                time_val = int.from_bytes(fs.getattr(fullpath, "t"), byteorder="little")
                time_str = datetime.fromtimestamp(time_val, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            except LittleFSError:
                time_str = " " * 19

            is_last_element = idx == (len(elements) - 1)
            indent = prefix
            if is_last_element:
                indent += "└── "
            else:
                indent += "├── "
            metadata = colored(Color.BLACK, f"[{element.size:7}B {typ} {time_str}]")
            print(f"{indent}{metadata} {colored(color, element.name)}")

            # Recursive call on subdirectory
            if element.type == 2 and depth < max_depth:
                next_prefix = prefix + ("    " if is_last_element else "│   ")
                _tree(fs, fullpath, depth + 1, max_depth, next_prefix)
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
    from .main import gnw

    fs = gnw.filesystem(offset=offset)
    _tree(fs, path.as_posix(), 0, depth)
