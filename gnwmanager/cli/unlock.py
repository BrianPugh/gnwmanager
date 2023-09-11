"""Unlock the factory Game & Watch device.

Based on:
    https://github.com/ghidraninja/game-and-watch-backup
"""

import hashlib
import importlib.resources
from contextlib import contextmanager, suppress
from datetime import datetime
from enum import Enum
from functools import lru_cache
from pathlib import Path
from time import sleep

from autoregistry import Registry
from typer import Argument, Option
from typing_extensions import Annotated

from gnwmanager.gnw import GnW


class HashMismatchError(Exception):
    """Data did not match expected hash."""


class AutodetectError(Exception):
    """Unable to autodetect device type."""


def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _xor(a: bytes, b: bytes) -> bytes:
    return bytearray(x ^ y for x, y in zip(a, b))


class DeviceModel(Registry, suffix="Model"):
    itcm_offset: int
    itcm_size: int

    itcm_hash: str
    internal_flash_hash: str
    external_flash_hash: str

    external_flash_hash_start: int
    external_flash_hash_end: int

    external_flash_size: int

    external_offset: int  # TODO: better name

    def __init__(self, gnw: GnW):
        self.gnw = gnw

    def __str__(self):
        return type(self).__registry__.name

    @lru_cache  # noqa: B019
    def read_itcm(self) -> bytes:
        data = self.gnw.read_memory(self.itcm_offset, self.itcm_size)
        self.validate_itcm(data)
        return data

    def validate_itcm(self, data):
        if _sha1(data) != self.itcm_hash:
            raise HashMismatchError

    @lru_cache  # noqa: B019
    def read_extflash(self) -> bytes:
        # TODO: for some reason reading large chunks errors out
        chunk_size = 256 << 10
        chunks = []
        for offset in range(0, self.external_flash_size, chunk_size):
            chunks.append(self.gnw.read_memory(0x9000_0000 + offset, chunk_size))
        data = b"".join(chunks)
        self.validate_extflash(data)
        return data

    def validate_extflash(self, data: bytes):
        hash_data = data[self.external_flash_hash_start : self.external_flash_hash_end]
        if _sha1(hash_data) != self.external_flash_hash:
            raise HashMismatchError

    def create_encrypted_payload(self, itcm: bytes, extflash: bytes, payload: bytes) -> bytes:
        self.validate_itcm(itcm)
        self.validate_extflash(extflash)
        output = bytearray(extflash)

        extflash_segment = extflash[self.external_offset : self.external_offset + len(payload)]
        xor_image = _xor(itcm[: len(payload)], extflash_segment)
        output[self.external_offset : self.external_offset + len(payload)] = _xor(payload, xor_image)
        return bytes(output)

    @classmethod
    def autodetect(cls, gnw: GnW):
        for device_constructor in DeviceModel.values():
            device = device_constructor(gnw)
            with suppress(HashMismatchError):
                device.read_itcm()
                return device

        raise AutodetectError


class MarioModel(DeviceModel):
    itcm_offset = 0
    itcm_size = 1300

    itcm_hash = "ca71a54c0a22cca5c6ee129faee9f99f3a346ca0"
    internal_flash_hash = "efa04c387ad7b40549e15799b471a6e1cd234c76"
    external_flash_hash = "eea70bb171afece163fb4b293c5364ddb90637ae"

    external_flash_hash_start = 0
    external_flash_hash_end = 0xF_E000

    external_flash_size = 1 << 20

    external_offset = 0


class ZeldaModel(DeviceModel):
    itcm_offset = 20
    itcm_size = 1300

    itcm_hash = "2f70156235ffd871599facf64457040d549353b4"
    internal_flash_hash = "ac14bcea6e4ff68c88fd2302c021025a2fb47940"
    external_flash_hash = "1c1c0ed66d07324e560dcd9e86a322ec5e4c1e96"

    external_flash_hash_start = 0x20000
    external_flash_hash_end = 0x3254A0

    external_flash_size = 4 << 20

    external_offset = 0x30C3A8


class GnWModel(str, Enum):
    mario = "mario"
    zelda = "zelda"


def unlock(
    backup_dir: Annotated[
        Path,
        Option(
            help="Output directory for backed up files.",
        ),
    ] = Path(
        f"backups-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"  # noqa: B008
    ),
    interactive: Annotated[
        bool,
        Option(
            help="Enable/Disable interactive prompts.",
        ),
    ] = True,
    backup: Annotated[
        bool,
        Option(
            help="Backup device contents first.",
        ),
    ] = True,
):
    """Backs up and unlocks a stock Game & Watch console."""
    from .main import gnw

    @contextmanager
    def message(msg):
        if interactive:
            print(msg + "... ", end="", flush=True)
        try:
            yield
        finally:
            if interactive:
                print("complete!")

    # TODO: this is deprecated, but the replacement was introduced in python3.9.
    # Migrate to ``as_file`` once python3.8 hits EOL.
    with importlib.resources.path("gnwmanager", "unlock.bin") as f:
        unlock_firmware_data = f.read_bytes()

    backup_dir.mkdir(exist_ok=True)

    device = DeviceModel.autodetect(gnw)
    model = str(device)

    itcm = backup_dir / f"itcm_backup_{model}.bin"
    extflash = backup_dir / f"flash_backup_{model}.bin"

    if backup:
        if itcm.exists():
            raise FileExistsError(f"Cannot backup to existing {itcm}")
        if extflash.exists():
            raise FileExistsError(f"Cannot backup to existing {extflash}")

    if interactive:
        print(f"Detected {model} game and watch.")

    if backup:
        with message(f'Backing up itcm to "{itcm}"'):
            itcm.write_bytes(device.read_itcm())

        with message(f'Backing up external flash to "{extflash}"'):
            extflash.write_bytes(device.read_extflash())

    # Read back in all data in-case we skipped backup.
    itcm_data = itcm.read_bytes()
    extflash_data = extflash.read_bytes()

    payload = device.create_encrypted_payload(itcm_data, extflash_data, unlock_firmware_data)
    breakpoint()

    with message("Flashing payload to external flash."):
        gnw.write_memory(0x9000_0000, payload)

    breakpoint()

    raise NotImplementedError
