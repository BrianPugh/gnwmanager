import logging
from pathlib import Path
from typing import List

from cyclopts import Parameter
from typing_extensions import Annotated

from gnwmanager.cli._parsers import GnWType, OffsetType
from gnwmanager.cli.main import app
from gnwmanager.filesystem import gnw_sha256, is_existing_gnw_dir
from gnwmanager.time import timestamp_now
from gnwmanager.utils import sha256

log = logging.getLogger(__name__)


@app.command
def push(
    gnw_path: Path,
    local_paths: Annotated[List[Path], Parameter(negative=[])],
    offset: OffsetType = 0,
    *,
    gnw: GnWType,
):
    """Push file(s) and folder(s) to device.

    Parameters
    ----------
    gnw_path: Path
        Game-and-watch file or folder to write to.
    local_paths: Path
        Local file(s) or folder to copy data to.
    offset: int
        Distance from the END of the filesystem, to the END of flash.
    """
    gnw.start_gnwmanager()

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

                log.info(f"Writing {len(data)} bytes to {dst.as_posix()}.")
                with fs.open(dst.as_posix(), "wb") as f:
                    f.write(data)
            else:
                log.info(f"No data changed for {dst.as_posix()}.")

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

                    log.info(f"Writing {len(data)} bytes to {dst.as_posix()}.")
                    with fs.open(dst.as_posix(), "wb") as f:
                        f.write(data)
                else:
                    log.info(f"No data changed for {dst.as_posix()}.")

                fs.setattr(dst.as_posix(), "t", timestamp_now().to_bytes(4, "little"))

    gnw.wait_for_all_contexts_complete()
