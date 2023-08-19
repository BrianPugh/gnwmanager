from datetime import datetime, timezone
from pathlib import Path

from littlefs import LittleFS, LittleFSError
from typer import Argument, Option
from typing_extensions import Annotated

from gnwmanager.cli._parsers import int_parser
from gnwmanager.filesystem import get_filesystem


def pull(
    gnw_path: Annotated[
        Path,
        Argument(
            help="Game-and-watch file or folder to copy to computer.",
        ),
    ],
    local_path: Annotated[
        Path,
        Argument(
            help="Local file or folder to copy data to.",
        ),
    ],
    offset: Annotated[
        int,
        Option(
            min=0,
            parser=int_parser,
            help="Distance in bytes from the END of the filesystem, to the END of flash.",
        ),
    ] = 0,
):
    """Pull a file or folder from device."""
    from .main import session

    target = session.target
    fs = get_filesystem(target, offset=offset)

    try:
        stat = fs.stat(gnw_path.as_posix())
    except LittleFSError as e:
        if e.code != -2:
            raise
        print(f"{gnw_path.as_posix()}: No such file or directory")
        return

    if stat.type == 1:  # file
        with fs.open(gnw_path.as_posix(), "rb") as f:
            data = f.read()
        if local_path.is_dir():
            local_path = local_path / gnw_path.name
        local_path.write_bytes(data)
    elif stat.type == 2:  # dir
        if local_path.is_file():
            raise ValueError(f'Cannot backup directory "{gnw_path.as_posix()}" to file "{local_path}"')

        strip_root = not local_path.exists()
        for root, _, files in fs.walk(gnw_path.as_posix()):
            root = Path(root.lstrip("/"))
            for file in files:
                full_src_path = root / file

                if strip_root:
                    full_dst_path = local_path / Path(*full_src_path.parts[1:])
                else:
                    full_dst_path = local_path / full_src_path

                full_dst_path.parent.mkdir(exist_ok=True, parents=True)

                with fs.open(full_src_path.as_posix(), "rb") as f:
                    data = f.read()

                full_dst_path.write_bytes(data)
    else:
        raise NotImplementedError(f"Unknown type: {stat.type}")
