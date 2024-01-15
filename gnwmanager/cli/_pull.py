import logging
from pathlib import Path

from littlefs.errors import LittleFSError

from gnwmanager.cli._parsers import GnWType, OffsetType
from gnwmanager.cli.main import app

log = logging.getLogger(__name__)


@app.command(group="Filesystem")
def pull(
    gnw_path: Path,
    local_path: Path,
    offset: OffsetType = 0,
    *,
    gnw: GnWType,
):
    """Pull a file or folder from device.

    Parameters
    ----------
    gnw_path: Path
        Game-and-watch file or folder to copy to computer.
    local_path: Path
        Local file or folder to copy data to.
    offset: int
        Distance from the END of the filesystem, to the END of flash.
    """
    gnw.start_gnwmanager()

    fs = gnw.filesystem(offset=offset)

    try:
        stat = fs.stat(gnw_path.as_posix())
    except LittleFSError as e:
        if e.code != -2:
            raise
        print(f"{gnw_path.as_posix()}: No such file or directory")
        return

    if stat.type == 1:  # file
        if local_path.is_dir():
            local_path = local_path / gnw_path.name
        log.info(f"Pulling FILE {gnw_path.as_posix()}  ->  {str(local_path)}.")

        with fs.open(gnw_path.as_posix(), "rb") as f:
            data = f.read()

        local_path.write_bytes(data)
    elif stat.type == 2:  # dir
        log.info(f"Pulling DIR {gnw_path.as_posix()}.")
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

                log.info(f"Pulling FILE {gnw_path.as_posix()}  ->  {str(full_dst_path)}.")

                with fs.open(full_src_path.as_posix(), "rb") as f:
                    data = f.read()

                full_dst_path.write_bytes(data)
    else:
        raise NotImplementedError(f"Unknown type: {stat.type}")
