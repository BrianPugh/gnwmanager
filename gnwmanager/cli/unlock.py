"""Unlock the factory Game & Watch device.

Based on:
    https://github.com/ghidraninja/game-and-watch-backup
"""

import hashlib
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


def _sha1(data) -> str:
    return hashlib.sha1(data).hexdigest()


class DeviceModel(Registry, suffix="Model"):
    itcm_offset: int
    itcm_size: int

    itcm_hash: str
    internal_flash_hash: str
    external_flash_hash: str

    external_flash_hash_start: int
    external_flash_hash_end: int

    external_flash_size: int

    def __init__(self, gnw: GnW):
        self.gnw = gnw
        self.gnw.backend.halt()
        self._init_qspi()

    def __str__(self):
        return type(self).__registry__.name

    @lru_cache  # noqa: B019
    def read_itcm(self) -> bytes:
        data = self.gnw.read_memory(self.itcm_offset, self.itcm_size)
        if _sha1(data) != self.itcm_hash:
            raise HashMismatchError

        return data

    @lru_cache  # noqa: B019
    def read_extflash(self) -> bytes:
        # TODO: for some reason reading chunks > 380KB errors out, to be investigated later
        chunk_size = 256 << 10  # 256KB
        chunks = []
        for offset in range(0, self.external_flash_size, chunk_size):
            chunks.append(self.gnw.read_memory(0x9000_0000 + offset, chunk_size))
        data = b"".join(chunks)
        hash_data = data[self.external_flash_hash_start : self.external_flash_hash_end]
        if _sha1(hash_data) != self.external_flash_hash:
            raise HashMismatchError
        return data

    @classmethod
    def autodetect(cls, gnw: GnW):
        for device_constructor in DeviceModel.values():
            device = device_constructor(gnw)
            with suppress(HashMismatchError):
                device.read_itcm()
                return device

        raise AutodetectError

    def _init_qspi(self):
        def mww(addr, value):
            self.gnw.write_uint32(addr, value)

        def mmw(addr, val, mask):
            current_val = self.gnw.read_uint32(addr)
            new_value = (current_val & ~mask) | val
            self.gnw.write_uint32(addr, new_value)

        # PB01: OCTOSPIM_P1_IO0, PD12: OCTOSPIM_P1_IO1, PE02: OCTOSPIM_P1_IO2,
        # PA01: OCTOSPIM_P1_IO3, PB02: OCTOSPIM_P1_CLK, PE11: OCTOSPIM_P1_NCS,
        # PD01: 1.8V power

        # Enable GPIO clocks
        mmw(0x58024540, 0x0000001B, 0x00000000)  # RCC_AHB4ENR |= GPIOAEN | GPIOBEN | GPIODEN | GPIOEEN
        # Enable Octo-SPI clocks
        mmw(0x58024534, 0x00204000, 0x00000000)  # RCC_AHB3ENR |= OCTOSPI1EN | OCTOSPIMEN (enable clocks)
        sleep(0.001)

        # Set GPIO ports (push-pull, no pull)
        # Port A: PA01:AF09:V
        mmw(0x58020000, 0x00000000, 0x00000004)  # GPIOA_MODER
        mmw(0x58020008, 0x0000000C, 0x00000000)  # GPIOA_OSPEEDR
        mmw(0x58020020, 0x00000090, 0x00000000)  # GPIOA_AFRL
        # Port B: PB01:AF11:V PB02:AF09:V
        mmw(0x58020400, 0x00000000, 0x00000014)  # GPIOB_MODER
        mmw(0x58020408, 0x0000003C, 0x00000000)  # GPIOB_OSPEEDR
        mmw(0x58020420, 0x000009B0, 0x00000000)  # GPIOB_AFRL
        # Port D: PD01:OP:L PD12:AF09:V
        mmw(0x58020C00, 0x00000000, 0x01000008)  # GPIOD_MODER
        mmw(0x58020C08, 0x03000000, 0x00000000)  # GPIOD_OSPEEDR
        mmw(0x58020C24, 0x00090000, 0x00000000)  # GPIOD_AFRH
        # Port E: PE02:AF09:V PE11:AF11:V
        mmw(0x58021000, 0x00000000, 0x00400010)  # GPIOE_MODER
        mmw(0x58021008, 0x00C00030, 0x00000000)  # GPIOE_OSPEEDR
        mmw(0x58021020, 0x00000900, 0x00000000)  # GPIOE_AFRL
        mmw(0x58021024, 0x0000B000, 0x00000000)  # GPIOE_AFRH

        # Reset Octo-SPI
        mmw(0x5802447C, 0x00204000, 0x00000000)  # RCC_AHB3RSTR |= OCTOSPIMRST | OCTOSPI1RST
        # Take Octo-SPI out of reset
        mmw(0x5802447C, 0x00000000, 0x00204000)  # RCC_AHB3RSTR &= ~(OCTOSPIMRST | OCTOSPI1RST)

        # Turn on 1.8v power
        mww(0x58020C18, 0x00010000)  # GPIOD_BSRR |= BR1

        # Set up Octo-SPI interface
        mww(0x52005000, 0x00000400)  # OCTOSPI_CR: FMODE=0x0, FTHRES=0x04
        mww(0x52005008, 0x011B0208)  # OCTOSPI_DCR1: MTYP=0x1, DEVSIZE=0x1B, CSHT=0x2, DLYBYP=0x1
        mww(0x5200500C, 0x00000002)  # OCTOSPI_DCR2: PRESCALER=0x02
        mmw(0x52005000, 0x00000001, 0x00000000)  # OCTOSPI_CR: EN=0x1

        # reset the Macronix flash
        mww(
            0x52005100, 0x00000001
        )  # OCTOSPI_CCR: no data, no address, no alternate bytes, instruction on a single line
        # indirect write mode without data, address and alternate bytes causes the following commands to be sent immediately
        mww(0x52005110, 0x00000066)  # OCTOSPI_IR: Reset-Enable (RSTEN)
        sleep(0.001)
        mww(0x52005110, 0x00000099)  # OCTOSPI_IR: Reset (RST)
        sleep(0.02)  # wait for the flash to come out of reset

        mmw(0x52005000, 0x30000000, 0x00000001)  # OCTOSPI_CR |= FMODE=0x3, &= ~EN

        # OCTOSPI1: memory-mapped 1-line read mode with 3-byte addresses
        mww(0x52005100, 0x01002101)  # OCTOSPI_CCR: DMODE=0x1, ABMODE=0x0, ADSIZE=0x2, ADMODE=0x1, ISIZE=0x0, IMODE=0x1
        mww(0x52005110, 0x00000003)  # OCTOSPI_IR: INSTR=READ
        mmw(0x52005000, 0x00000001, 0x00000000)  # OCTOSPI_CR |= EN


class MarioModel(DeviceModel):
    itcm_offset = 0
    itcm_size = 1300

    itcm_hash = "ca71a54c0a22cca5c6ee129faee9f99f3a346ca0"
    internal_flash_hash = "efa04c387ad7b40549e15799b471a6e1cd234c76"
    external_flash_hash = "eea70bb171afece163fb4b293c5364ddb90637ae"

    external_flash_hash_start = 0
    external_flash_hash_end = 0xF_E000

    external_flash_size = 1 << 20


class ZeldaModel(DeviceModel):
    itcm_offset = 20
    itcm_size = 1300

    itcm_hash = "2f70156235ffd871599facf64457040d549353b4"
    internal_flash_hash = "ac14bcea6e4ff68c88fd2302c021025a2fb47940"
    external_flash_hash = "1c1c0ed66d07324e560dcd9e86a322ec5e4c1e96"

    external_flash_hash_start = 0x20000
    external_flash_hash_end = 0x3254A0

    external_flash_size = 4 << 20


class GnWModel(str, Enum):
    mario = "mario"
    zelda = "zelda"


def unlock(
    output: Annotated[
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

    if interactive:
        input("Make sure your Game & Watch is turned on and in the time screen. Press return when ready! ")

    output.mkdir()

    device = DeviceModel.autodetect(gnw)
    model = str(device)

    if interactive:
        print(f"Detected {model} game and watch.")

    if backup:
        itcm = output / f"itcm_backup_{model}.bin"
        with message(f'Backing up itcm to "{itcm}"'):
            itcm.write_bytes(device.read_itcm())

        external_flash = output / f"flash_backup_{model}.bin"
        with message(f'Backing up external flash to "{external_flash}"'):
            external_flash.write_bytes(device.read_extflash())

    raise NotImplementedError
