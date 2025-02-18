"""
Start      End        Description
---------- ---------- --------------------------------
0x00000    0x00090    If cleared, factory start. Stores Vermin score.
0x01000    0x01090    ^ second bank

0x02000    0x02B20    LA JP Save1
0x03000    0x03B20    LA JP Save2
0x04000    0x04B20    LA EN Save1
0x05000    0x05B20    LA EN Save2
0x06000    0x06B20    LA FR Save1
0x07000    0x07B20    LA FR Save2
0x08000    0x08B20    LA DE Save1
0x09000    0x09B20    LA DE Save2

0x0A000    0x0A560    LoZ1 EN Save1
0x0B000    0x0B560    LoZ1 EN Save2
0x0C000    0x0C540    LoZ1 JP Save1
0x0D000    0x0D540    LoZ1 JP Save2

0x0E000    0x0E360    LoZ2 EN Save1
0x0F000    0x0F360    LoZ2 EN Save2
0x10000    0x10360    LoZ2 JP Save1
0x11000    0x11360    LoZ2 JP Save2

0x12000    0x13000    Factory Test Scratch Pad

0x13000    0z20000    Empty

0x20000    0x30000    Sprites?

0x30000    0x50000    LoZ1 EN ROM
0x50000    0x70000    LoZ1 JP ROM

0x70000    0xB0000    LoZ2 EN ROM
0xB0000    0xD0000    LoZ2 JP ROM

0xD0000    0xD2000    LoZ2 Timer stuff?

0xD2000    0x1F4C00   LA ROMs (1,190,912 bytes)

0x1f4c00   0x288120   The 11 Backdrop Images (603,424 bytes)

0x288120   0x325490   External FW Data (643,952 bytes)

0x325490   0x3E0000   Empty  (764,784 bytes)

0x3E0000   0x3E8000   Cleared when you reset the GW
0x3E8000   0x3F0000   Launched LA, didn't save. Generic GB stuff?
0x3F0000   0x400000   Empty
"""

import logging

from .exception import InvalidStockRomError
from .firmware import Device, ExtFirmware, Firmware, IntFirmware

log = logging.getLogger(__name__)


class ZeldaGnW(Device, name="zelda"):
    class Int(IntFirmware):
        STOCK_ROM_SHA1_HASH = "ac14bcea6e4ff68c88fd2302c021025a2fb47940"
        STOCK_ROM_END = 0x1B3E0  # Used for generating linker script.
        KEY_OFFSET = 0x165A4
        NONCE_OFFSET = 0x16590
        RWDATA_OFFSET = 0x1B390
        RWDATA_LEN = 20
        RWDATA_DTCM_IDX = 0  # decompresses to 0x2000_A800

    class Ext(ExtFirmware):
        STOCK_ROM_SHA1_HASH = "1c1c0ed66d07324e560dcd9e86a322ec5e4c1e96"
        ENC_START = 0x20000
        ENC_END = 0x3254A0

        def _verify(self):
            h = self.hash(self[self.ENC_START : self.ENC_END])
            if h != self.STOCK_ROM_SHA1_HASH:
                raise InvalidStockRomError

    class FreeMemory(Firmware):
        FLASH_BASE = 0x240F2124
        FLASH_LEN = 0  # 0x24100000 - FLASH_BASE

    def _disable_save_encryption(self):
        # Skip ingame save encryption
        self.internal.nop(0xF222, 1)
        self.internal.asm(0xF228, "add.w r2,r1,#0x10")
        self.internal.asm(0xF22C, "sub.w r1,r8,#0x10")

        # Skip LA save state encryption
        self.internal.b(0x13ED8, 0x13F06)

        # Skip NVRAM (system settings and vermin save) encryption
        self.internal.asm(0xB5C4, "mov r1,r2")
        self.internal.nop(0xB5C6, 1)
        self.internal.nop(0xB5CC, 1)

        # Skip ingame save decryption
        self.internal.asm(0xF12C, "add.w r7,r0,#0x10")
        self.internal.asm(0xF130, "mov   r5,r1")
        self.internal.asm(0xF132, "sub.w r6,r2,#0x10")
        self.internal.asm(0xF136, "sub   sp,#0x10")
        self.internal.asm(0xF138, "mov   r1,r6")
        self.internal.asm(0xF13A, "mov   r0,r7")
        self.internal.replace(0xF13C, b"\xf4\xf7\xbc\xfc")
        self.internal.asm(0xF140, "mov   r2,r7")
        self.internal.asm(0xF142, "mov   r1,r6")
        self.internal.asm(0xF144, "mov   r0,r5")
        self.internal.replace(0xF146, b"\xfc\xf7\x29\xfc")
        self.internal.b(0xF14A, 0xF172)

        # Skip LA save state decryption
        self.internal.b(0x13F52, 0x13F94)

        # Skip NVRAM (system settings and vermin save) decryption
        self.internal.asm(0xB528, "mov r7,r0")
        self.internal.nop(0xB52A, 1)
        self.internal.replace(0xB54C, b"\xc0\xb1")

    def _erase_savedata(self):
        self.external.set_range(0x0000, 0x12000, b"\xFF")
        self.external.set_range(0x3E_8000, 0x3F_0000, b"\xFF")

    def patch(self):
        b_w_memcpy_inflate_asm = "b.w #" + hex(0xFFFFFFFE & self.internal.address("memcpy_inflate"))

        self._erase_savedata()

        self._disable_save_encryption()

        log.debug("Invoke custom bootloader prior to calling stock Reset_Handler.")
        self.internal.replace(0x4, "bootloader")

        log.debug("Intercept button presses for macros.")
        self.internal.bl(0xFE54, "read_buttons")

        # Disable OTFDEC
        self.internal.nop(0x16536, 2)
        self.internal.nop(0x1653A, 1)
        self.internal.nop(0x1653C, 1)

        if self.args.no_hour_tune:
            # Disable TIME/CLOCK hour tune
            # Change 'bne' to 'b'. Will replace the 'hour tune' with a 'second beep'
            self.external[0x320025] = 0xE0

        if self.args.no_second_beep:
            # Disable TIME/CLOCK second beep
            self.external.nop(0x32002E, 1)

        log.debug("Compressing and moving LoZ2 TIMER data to int")
        compressed_len = self.external.compress(0xD_0000, 0x2000)
        self.internal.asm(0xF430, b_w_memcpy_inflate_asm)
        self.move_to_int(0xD_0000, compressed_len, 0xFCF8)

        if self.args.no_la:
            log.debug("Removing Link's Awakening (All Languages)")
            self.external.clear_range(0xD2000, 0x1F4C00)
            self.external[0x315B54] = 0x00  # Ignore LA EN menu selection
            self.external[0x315B58] = 0x00  # Ignore LA FR menu selection
            self.external[0x315B5C] = 0x00  # Ignore LA DE menu selection
            self.external[0x315B60] = 0x00  # Ignore LA JP menu selection
            # TODO: make this work with moving stuff around, currently just
            # removing to free up an island of space.

        if self.args.no_sleep_images:
            self.external.clear_range(0x1F4C00, 0x288120)

            # setting this to NULL doesn't just display a black image, I
            # don't think the drawing code has a NULL check.
            # self.rwdata_erase(0x1f4c00, 0x288120 - 0x1f4c00)

            # TODO: make this work with moving stuff around, currently just
            # removing to free up an island of space.

        # Compress, insert, and reference the modified rwdata
        self.int_pos += self.internal.rwdata.write_table_and_data(0x1B070, data_offset=self.int_pos)

        internal_remaining_free = len(self.internal) - self.int_pos
        compressed_memory_free = len(self.compressed_memory) - self.compressed_memory_pos

        return internal_remaining_free, compressed_memory_free
