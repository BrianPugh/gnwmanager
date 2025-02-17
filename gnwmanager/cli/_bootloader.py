import logging
from typing import Annotated

import httpx
from cyclopts import Parameter

from gnwmanager.cli._flash import flash
from gnwmanager.cli._parsers import GnWType, OffsetType, convert_location, validate_internal_flash_range
from gnwmanager.cli.main import app, find_cache_folder

log = logging.getLogger(__name__)


def _resolve_latest_tag(repo) -> str:
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {"Accept": "application/vnd.github.v3+json"}
    with httpx.Client() as client:
        response = client.get(api_url, headers=headers)
        response.raise_for_status()

        # Extract tag name and asset URL
        release_data = response.json()
        tag = release_data["tag_name"]
    return tag


@app.command
def flash_bootloader(
    location: Annotated[
        int,
        Parameter(
            validator=validate_internal_flash_range,
            converter=convert_location,
        ),
    ],
    offset: OffsetType = 0,
    *,
    gnw: GnWType,
    repo: str = "sylverb/game-and-watch-bootloader",
    tag: str = "latest",
):
    """Download & flash pre-compiled SylverB's bootloader.

    https://github.com/sylverb/game-and-watch-bootloader

    Parameters
    ----------
    location: Union[int, Literal["bank1", "bank2"]]
        Either an absolute flash address (e.g. 0x08000000) or one of {bank1, bank2}.
    offset: int
        Offset into flash.
    repo: str
        Username/Repo to download the release from.
        Defaults to sylverb/game-and-watch-bootloader
    tag: str
        Version tag to download from (e.g. v1.0.2)
        Defaults to "latest".
    """
    if tag == "latest":
        tag = _resolve_latest_tag(repo)

    cache_folder = find_cache_folder() / "bootloader" / repo
    cache_folder.mkdir(parents=True, exist_ok=True)

    file_path = cache_folder / f"{tag}.bin"
    if not file_path.exists() or file_path.stat().st_size == 0:
        # Download a new copy
        with httpx.Client(follow_redirects=True) as client:
            download_url = f"https://github.com/{repo}/releases/download/{tag}/gnw_bootloader.bin"
            response = client.get(download_url)
            response.raise_for_status()
            file_path.write_bytes(response.content)

    log.info(f"Flashing bootloader {file_path}")
    # Flash it to device
    flash(location, file_path, offset=offset, gnw=gnw)
