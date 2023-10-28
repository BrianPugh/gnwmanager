from pathlib import Path
from typing import List

from typer import Argument, Option
from typing_extensions import Annotated

from gnwmanager.cli._parsers import int_parser
from gnwmanager.filesystem import get_filesystem, gnw_sha256, is_existing_gnw_dir
from gnwmanager.time import timestamp_now
from gnwmanager.utils import sha256


def push(
    gnw_path: Annotated[
        Path,
        Argument(
            show_default=False,
            help="Game-and-watch file or folder to write to.",
        ),
    ],
    local_paths: Annotated[
        List[Path],
        Argument(
            show_default=False,
            help="Local file or folder to copy data from.",
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
    """Push file(s) and folder(s) to device."""
    from .main import gnw

    fs = gnw.filesystem(offset=offset)

    gnw_path_is_dir = True if len(local_paths) > 1 else is_existing_gnw_dir(fs, gnw_path)

    for local_path in local_paths:
        if not local_path.exists():
            raise ValueError(f'Local "{local_path}" does not exist.')

        if local_path.is_file():
            data = local_path.read_bytes()

            dst = gnw_path / local_path.name if gnw_path_is_dir else gnw_path

            if sha256(data) != gnw_sha256(fs, dst):
                fs.makedirs(dst.parent.as_posix(), exist_ok=True)

                with fs.open(dst.as_posix(), "wb") as f:
                    f.write(data)

            fs.setattr(dst.as_posix(), "t", timestamp_now().to_bytes(4, "little"))
        else:
            for file in local_path.rglob("*"):
                if file.is_dir():
                    continue
                data = file.read_bytes()

                subpath = file.relative_to(local_path.parent)
                dst = gnw_path / Path(*subpath.parts[1:]) if not gnw_path_is_dir else gnw_path / subpath

                if sha256(data) != gnw_sha256(fs, dst):
                    fs.makedirs(dst.parent.as_posix(), exist_ok=True)

                    with fs.open(dst.as_posix(), "wb") as f:
                        f.write(data)

                fs.setattr(dst.as_posix(), "t", timestamp_now().to_bytes(4, "little"))

    gnw.wait_for_all_contexts_complete()
