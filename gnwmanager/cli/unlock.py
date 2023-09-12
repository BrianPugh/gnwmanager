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
from typing import Optional

from autoregistry import Registry
from typer import Argument, Option
from typing_extensions import Annotated

from gnwmanager.gnw import GnW

_payload_flash_msg = """

Payload successfully flashed. Perform the following steps:

1. Fully remove power, then re-apply power.
2. Press the power button to turn on the device; the screen should turn blue.
"""


class HashMismatchError(Exception):
    """Data did not match expected hash."""

    def __init__(self, expected: str, actual: str):
        self.expected = expected
        self.actual = actual
        super().__init__(f"Hash mismatch: Expected '{self.expected}', but got '{self.actual}'.")


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
        actual_hash = _sha1(data)
        if actual_hash != self.itcm_hash:
            raise HashMismatchError(self.itcm_hash, actual_hash)

    @lru_cache  # noqa: B019
    def read_external_flash(self) -> bytes:
        # TODO: for some reason reading large chunks errors out
        chunk_size = 256 << 10
        chunks = []
        for offset in range(0, self.external_flash_size, chunk_size):
            chunks.append(self.gnw.read_memory(0x9000_0000 + offset, chunk_size))
        data = b"".join(chunks)
        self.validate_external_flash(data)
        return data

    def validate_external_flash(self, data: bytes):
        hash_data = data[self.external_flash_hash_start : self.external_flash_hash_end]
        actual_hash = _sha1(hash_data)
        if actual_hash != self.external_flash_hash:
            raise HashMismatchError(self.external_flash_hash, actual_hash)

    def read_internal_from_ram(self):
        """Reads flash dump from RAM (put there by payload).

        Internal flash is not directly readable under RDP1.
        Our payload adds some code to extflash, that gets loaded into ITCM RAM on boot.
        Since the device doesn't see a debugger attached, that code is allowed to access
        the internal flash bank and copy it's contents to SRAM, where a debugger is allowed
        to copy it to a computer.
        """
        data = self.gnw.backend.read_memory(0x2400_0000, 128 << 10)
        Path("internal_dump.bin").write_bytes(data)  # TODO: remove
        self.validate_internal_flash(data)
        return data

    def validate_internal_flash(self, data):
        actual_hash = _sha1(data)
        if actual_hash != self.internal_flash_hash:
            raise HashMismatchError(self.internal_flash_hash, actual_hash)

    def create_encrypted_payload(self, itcm: bytes, extflash: bytes, payload: bytes) -> bytes:
        self.validate_itcm(itcm)
        self.validate_external_flash(extflash)
        output = bytearray(extflash)  # Create an editable copy

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
        Optional[Path],
        Option(
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
            writable=True,
            help="Output directory for backed up files.",
        ),
    ] = None,
    interactive: Annotated[
        bool,
        Option(
            help="Enable/Disable interactive prompts.",
        ),
    ] = True,
    model: Annotated[  # pyright: ignore [reportGeneralTypeIssues]
        Optional[GnWModel],
        Option(
            help="Defaults to autodetecting.",
        ),
    ] = None,
    skip_itcm: Annotated[
        bool,
        Option(
            help="Skip backing up itcm ram. Existing backup must be present.",
        ),
    ] = False,
    skip_internal: Annotated[
        bool,
        Option(
            help="Skip backing up internal flash. Existing backup must be present.",
        ),
    ] = False,
    skip_external: Annotated[
        bool,
        Option(
            help="Skip backing up external flash. Existing backup must be present.",
        ),
    ] = False,
):
    """Backs up and unlocks a stock Game & Watch console."""
    from .main import gnw

    if backup_dir is None:
        backup_dir = Path(f"backups-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}")
    backup_dir.mkdir(exist_ok=True)

    @contextmanager
    def message(msg):
        if interactive:
            print(msg + "... ", end="", flush=True)
        try:
            yield
        finally:
            if interactive:
                print("complete!")

    if model is not None:
        model: str = model.value

    # TODO: this is deprecated, but the replacement was introduced in python3.9.
    # Migrate to ``as_file`` once python3.8 hits EOL.
    with importlib.resources.path("gnwmanager", "unlock.bin") as f:
        unlock_firmware_data = f.read_bytes()

    if model is None:
        device = DeviceModel.autodetect(gnw)
        model = str(device)
    else:
        device = DeviceModel[model](gnw)

    itcm = backup_dir / f"itcm_backup_{model}.bin"
    external_flash = backup_dir / f"flash_backup_{model}.bin"
    internal_flash = backup_dir / f"internal_flash_backup_{model}.bin"

    if skip_itcm:
        if not itcm.exists():
            raise ValueError("No backup of itcm is present.")
    else:
        if itcm.exists():
            raise FileExistsError(f"Cannot backup to existing {itcm}")

    if skip_external:
        if not external_flash.exists():
            raise ValueError("No backup of external flash is present.")
    else:
        if external_flash.exists():
            raise FileExistsError(f"Cannot backup to existing {external_flash}")

    if skip_internal:
        if not internal_flash.exists():
            raise ValueError("No backup of internal flash is present.")
    else:
        if internal_flash.exists():
            raise FileExistsError(f"Cannot backup to existing {internal_flash}")

    if interactive:
        print(f"Detected {model} game and watch.")

    if not skip_itcm:
        with message(f'Backing up itcm to "{itcm}"'):
            itcm.write_bytes(device.read_itcm())

    if not skip_external:
        with message(f'Backing up external flash to "{external_flash}"'):
            external_flash.write_bytes(device.read_extflash())

    # Read back in all data in-case we skipped backup.
    itcm_data = itcm.read_bytes()
    external_flash_data = external_flash.read_bytes()

    if not skip_internal:
        payload = device.create_encrypted_payload(itcm_data, external_flash_data, unlock_firmware_data)
        Path("enc_payload.bin").write_bytes(payload)  # TODO: remove

        with message("Flashing payload to external flash."):
            gnw.flash(0, 0, payload)

        # Close connection in preparation for power removal
        gnw.backend.close()

        print(_payload_flash_msg)
        input('Press the "enter" key to continue: ')

        gnw.backend.open()
        gnw.backend.halt()

        with message(f'Backing up internal flash to "{internal_flash}"'):
            internal_flash.write_bytes(device.read_internal_from_ram())

    raise NotImplementedError
