import hashlib
import logging
from contextlib import suppress
from functools import lru_cache
from pathlib import Path

from autoregistry import Registry

from gnwmanager.gnw import GnW

log = logging.getLogger(__name__)


class AutodetectError(Exception):
    """Unable to autodetect device type."""


class HashMismatchError(Exception):
    """Data did not match expected hash."""

    def __init__(self, expected: str, actual: str):
        self.expected = expected
        self.actual = actual
        super().__init__(f"Hash mismatch: Expected '{self.expected}', but got '{self.actual}'.")


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

    external_offset: int

    def __init__(self, gnw: GnW):
        self.gnw = gnw

    def __str__(self):
        return type(self).__registry__.name

    @lru_cache  # noqa: B019
    def read_itcm(self) -> bytes:
        data = self.gnw.read_memory(self.itcm_offset, self.itcm_size)
        self.validate_itcm(data)
        return data

    @classmethod
    def validate_itcm(cls, data):
        actual_hash = _sha1(data)
        log.debug(f"Actual ITCM Hash: {actual_hash}")
        if actual_hash != cls.itcm_hash:
            raise HashMismatchError(cls.itcm_hash, actual_hash)

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

    @classmethod
    def validate_external_flash(cls, data: bytes):
        hash_data = data[cls.external_flash_hash_start : cls.external_flash_hash_end]
        actual_hash = _sha1(hash_data)
        log.debug(f"Actual External Flash Hash: {actual_hash}")
        if actual_hash != cls.external_flash_hash:
            raise HashMismatchError(cls.external_flash_hash, actual_hash)

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

    @classmethod
    def validate_internal_flash(cls, data):
        actual_hash = _sha1(data)
        log.debug(f"Actual Internal Flash Hash: {actual_hash}")
        if actual_hash != cls.internal_flash_hash:
            raise HashMismatchError(cls.internal_flash_hash, actual_hash)

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
    itcm_offset = 0x20
    itcm_size = 1300

    itcm_hash = "2f70156235ffd871599facf64457040d549353b4"
    internal_flash_hash = "ac14bcea6e4ff68c88fd2302c021025a2fb47940"
    external_flash_hash = "1c1c0ed66d07324e560dcd9e86a322ec5e4c1e96"

    external_flash_hash_start = 0x20000
    external_flash_hash_end = 0x3254A0

    external_flash_size = 4 << 20

    external_offset = 0x30C3A8
