from pathlib import Path

from .exception import InvalidStockRomError
from .firmware import Device, ExtFirmware, Firmware, IntFirmware
from .utils import (
    printd,
    printe,
    printi,
    round_down_word,
    round_up_page,
    seconds_to_frames,
)


class MarioGnW(Device, name="mario"):
    class Int(IntFirmware):
        STOCK_ROM_SHA1_HASH = "efa04c387ad7b40549e15799b471a6e1cd234c76"

        # Note: this isn't the ACTUAL Stock ROM end, this is actually
        # pointing to where some rwdata is, but this data will be relocated
        # and compressed. This variable is used in the linker scripts as to
        # where to start putting novel code.
        STOCK_ROM_END = 0x18100
        KEY_OFFSET = 0x106F4
        NONCE_OFFSET = 0x106E4
        RWDATA_OFFSET = 0x180A4
        RWDATA_LEN = 36
        RWDATA_ITCM_IDX = 0
        RWDATA_DTCM_IDX = 1

    class Ext(ExtFirmware):
        STOCK_ROM_SHA1_HASH = "eea70bb171afece163fb4b293c5364ddb90637ae"
        ENC_END = 0xF_E000

        def _verify(self):
            h = self.hash(self[:-8192])
            if h != self.STOCK_ROM_SHA1_HASH:
                raise InvalidStockRomError

    class FreeMemory(Firmware):
        FLASH_BASE = 0x240F2124
        FLASH_LEN = 0x24100000 - FLASH_BASE

    def patch(self):
        printi("Invoke custom bootloader prior to calling stock Reset_Handler.")
        self.internal.replace(0x4, "bootloader")

        printi("Intercept button presses for macros.")
        self.internal.bl(0x6B52, "read_buttons")

        printi("Mute clock audio on first boot.")
        self.internal.asm(0x49E0, "mov.w r1, #0x00000")

        if self.args.sleep_time:
            printi(f"Setting sleep time to {self.args.sleep_time} seconds.")
            sleep_time_frames = seconds_to_frames(self.args.sleep_time)
            self.internal.asm(0x6C3C, f"movw r2, #{sleep_time_frames}")

        if self.args.disable_sleep:
            printi("Disable sleep timer")
            self.internal.replace(0x6C40, 0x91, size=1)

        # Disable OTFDEC
        self.internal.nop(0x10688, 2)
        self.internal.nop(0x1068E, 1)

        printd("Compressing and moving stuff stuff to internal firmware.")
        compressed_len = self.external.compress(
            0x0, 7772
        )  # Dst expects only 7772 bytes, not 7776
        self.internal.bl(0x665C, "memcpy_inflate")
        self.move_ext(0x0, compressed_len, 0x7204)
        # Note: the 4 bytes between 7772 and 7776 is padding.
        self.ext_offset -= 7776 - round_down_word(compressed_len)

        # SMB1 ROM
        printd("Compressing and moving SMB1 ROM to compressed_memory.")
        smb1_addr, smb1_size = 0x1E60, 40960
        patch_smb1_refr = self.internal.address("SMB1_ROM", sub_base=True)
        self.move_to_compressed_memory(
            smb1_addr, smb1_size, [0x7368, 0x10954, 0x7218, patch_smb1_refr]
        )

        # I think these are all scenes for the clock, but not 100% sure.
        # The giant lookup table references all these
        self.move_to_compressed_memory(0xBE60, 11620, None)

        # Starting here are BALL references
        self.move_to_compressed_memory(0xEBC4, 528, 0x4154)
        self.rwdata_lookup(0xEBC4, 528)

        self.move_to_compressed_memory(0xEDD4, 100, 0x4570)

        references = {
            0xEE38: 0x4514,
            0xEE78: 0x4518,
            0xEEB8: 0x4520,
            0xEEF8: 0x4524,
        }
        for external, internal in references.items():
            self.move_to_compressed_memory(external, 64, internal)

        references = [
            0x2AC,
            0x2B0,
            0x2B4,
            0x2B8,
            0x2BC,
            0x2C0,
            0x2C4,
            0x2C8,
            0x2CC,
            0x2D0,
        ]
        self.move_to_compressed_memory(0xEF38, 128 * 10, references)

        self.move_to_compressed_memory(0xF438, 96, 0x456C)
        self.move_to_compressed_memory(0xF498, 180, 0x43F8)

        # This is the first thing passed into the drawing engine.
        self.move_to_compressed_memory(0xF54C, 1100, 0x43FC)
        self.move_to_compressed_memory(0xF998, 180, 0x4400)
        self.move_to_compressed_memory(0xFA4C, 1136, 0x4404)
        self.move_to_compressed_memory(0xFEBC, 864, 0x450C)
        self.move_to_compressed_memory(0x1_021C, 384, 0x4510)
        self.move_to_compressed_memory(0x1_039C, 384, 0x451C)
        self.move_to_compressed_memory(0x1_051C, 384, 0x4410)
        self.move_to_compressed_memory(0x1_069C, 384, 0x44F8)
        self.move_to_compressed_memory(0x1_081C, 384, 0x4500)
        self.move_to_compressed_memory(0x1_099C, 384, 0x4414)
        self.move_to_compressed_memory(0x1_0B1C, 384, 0x44FC)
        self.move_to_compressed_memory(0x1_0C9C, 384, 0x4504)
        self.move_to_compressed_memory(0x1_0E1C, 384, 0x440C)
        self.move_to_compressed_memory(0x1_0F9C, 384, 0x4408)
        self.move_to_compressed_memory(0x1_111C, 192, 0x44F4)
        self.move_to_compressed_memory(0x1_11DC, 192, 0x4508)
        self.move_to_compressed_memory(0x1_129C, 304, 0x458C)
        self.move_to_compressed_memory(
            0x1_13CC, 768, 0x4584
        )  # BALL logo tile idx tight
        self.move_to_compressed_memory(0x1_16CC, 1144, 0x4588)
        self.move_to_compressed_memory(0x1_1B44, 768, 0x4534)
        self.move_to_compressed_memory(0x1_1E44, 32, 0x455C)
        self.move_to_compressed_memory(0x1_1E64, 32, 0x4558)
        self.move_to_compressed_memory(0x1_1E84, 32, 0x4554)
        self.move_to_compressed_memory(0x1_1EA4, 32, 0x4560)
        self.move_to_compressed_memory(0x1_1EC4, 32, 0x4564)
        self.move_to_compressed_memory(0x1_1EE4, 64, 0x453C)
        self.move_to_compressed_memory(0x1_1F24, 64, 0x4530)
        self.move_to_compressed_memory(0x1_1F64, 64, 0x4540)
        self.move_to_compressed_memory(0x1_1FA4, 64, 0x4544)
        self.move_to_compressed_memory(0x1_1FE4, 64, 0x4548)
        self.move_to_compressed_memory(0x1_2024, 64, 0x454C)
        self.move_to_compressed_memory(0x1_2064, 64, 0x452C)
        self.move_to_compressed_memory(0x1_20A4, 64, 0x4550)

        self.move_to_compressed_memory(0x1_20E4, 21 * 96, 0x4574)
        self.move_to_compressed_memory(0x1_28C4, 192, 0x4578)
        self.move_to_compressed_memory(0x1_2984, 640, 0x457C)

        # This is a 320 byte palette used for BALL, but the last 160 bytes are empty
        self.move_to_compressed_memory(0x1_2C04, 320, 0x4538)

        mario_song_len = 0x85E40  # 548,416 bytes
        if self.args.no_mario_song:
            # This isn't really necessary, but we keep it here because its more explicit.
            printe("Erasing Mario Song")
            self.external.replace(0x1_2D44, b"\x00" * mario_song_len)
            self.rwdata_erase(0x1_2D44, mario_song_len)
            self.ext_offset -= mario_song_len

            self.internal.asm(0x6FC8, "b 0x1c")
        else:
            references = [
                # Banners
                0x11A00,
                0x11A00 + 4,
                0x11A00 + 8,
                0x11A00 + 12,
                0x11A00 + 16,
                0x11A00 + 20,
                0x11A00 + 24,
                # Audio
                0x1199C,
            ]
            self.move_ext(0x1_2D44, mario_song_len, references)
            self.rwdata_lookup(0x1_2D44, mario_song_len)

        # Each tile is 16x16 pixels, stored as 256 bytes in row-major form.
        # These index into one of the palettes starting at 0xbec68.
        printe("Compressing clock graphics")
        compressed_len = self.external.compress(0x9_8B84, 0x1_0000)
        self.internal.bl(0x678E, "memcpy_inflate")

        printe("Moving clock graphics")
        self.move_ext(0x9_8B84, compressed_len, 0x7350)
        self.ext_offset -= 0x1_0000 - round_down_word(compressed_len)

        # Note: the clock uses a different palette; this palette only applies
        # to ingame Super Mario Bros 1 & 2
        printe("Moving NES emulator palette.")
        self.move_to_compressed_memory(0xA_8B84, 192, 0xB720)

        # Note: UNKNOWN* represents a block of data that i haven't decoded
        # yet. If you know what the block of data is, please let me know!
        self.move_to_compressed_memory(0xA_8C44, 8352, 0xBC44)

        printe("Moving iconset.")
        # MODIFY THESE IF WE WANT CUSTOM GAME ICONS
        self.move_to_compressed_memory(0xA_ACE4, 16128, [0xCEA8, 0xD2F8])

        printe("Moving menu stuff (icons? meta?)")
        references = [
            0x0_D010,
            0x0_D004,
            0x0_D2D8,
            0x0_D2DC,
            0x0_D2F4,
            0x0_D2F0,
        ]
        self.move_to_compressed_memory(0xA_EBE4, 116, references)

        smb2_addr, smb2_size = 0xA_EC58, 0x1_0000

        printe("Compressing and moving SMB2 ROM.")
        compressed_len = self.external.compress(smb2_addr, smb2_size)
        self.internal.bl(0x6A12, "memcpy_inflate")
        self.move_to_compressed_memory(smb2_addr, compressed_len, 0x7374)
        self.ext_offset -= smb2_size - round_down_word(
            compressed_len
        )  # Move by the space savings.

        # Round to nearest page so that the length can be used as an imm
        compressed_len = round_up_page(compressed_len)

        # Update the length of the compressed data (doesn't matter if its too large)
        self.internal.asm(0x6A0A, f"mov.w r2, #{compressed_len}")
        self.internal.asm(0x6A1E, f"mov.w r3, #{compressed_len}")

        # Not sure what this data is
        self.move_to_compressed_memory(0xBEC58, 8 * 2, 0x10964)

        printe("Moving Palettes")
        # There are 80 colors, each in BGRA format, where A is always 0
        # These are referenced by the scene table.
        self.move_to_compressed_memory(0xBEC68, 320, None)  # Day palette [0600, 1700]
        self.move_to_compressed_memory(0xBEDA8, 320, None)  # Night palette [1800, 0400)
        self.move_to_compressed_memory(
            0xBEEE8, 320, None
        )  # Underwater palette (between 1200 and 2400 at XX:30)
        self.move_to_compressed_memory(
            0xBF028, 320, None
        )  # Unknown palette. Maybe bowser castle? need to check...
        self.move_to_compressed_memory(0xBF168, 320, None)  # Dawn palette [0500, 0600)

        # These are scene headers, each containing 2x uint32_t's.
        # They are MOSTLY [0x36, 0xF], but there are a few like [0x30, 0xF] and [0x20, 0xF],
        # Referenced by the scene table
        self.move_to_compressed_memory(0xBF2A8, 45 * 8, None)

        # IDK what this is.
        self.move_to_compressed_memory(0xBF410, 144, 0x1658C)

        # SCENE TABLE
        # Goes in chunks of 20 bytes (5 addresses)
        # Each scene is represented by 5 pointers:
        #    1. Pointer to a 2x uint32_t header (I think it's total tile (w, h) )
        #            The H is always 15, which would be 240 pixels tall.
        #            The W is usually 54, which would be 864 pixels (probably the flag pole?)
        #    2. RLE something. Usually 32 bytes.
        #    3. RLE something
        #    4. RLE something
        #    5. Palette
        #
        # The RLE encoded data could be background tilemap, animation routine, etc.
        lookup_table_start = 0xB_F4A0
        lookup_table_end = 0xB_F838
        lookup_table_len = lookup_table_end - lookup_table_start  # 46 * 5 * 4 = 920
        for addr in range(lookup_table_start, lookup_table_end, 4):
            self.external.lookup(addr)

        # Now move the table
        self.move_to_compressed_memory(lookup_table_start, lookup_table_len, 0xDF88)

        # Not sure what this is
        references = [
            0xE8F8,
            0xF4EC,
            0xF4F8,
            0x10098,
            0x105B0,
        ]
        self.move_to_compressed_memory(0xBF838, 280, references)

        self.move_to_compressed_memory(0xBF950, 180, [0xE2E4, 0xF4FC])
        self.move_to_compressed_memory(0xBFA04, 8, 0x1_6590)
        self.move_to_compressed_memory(0xBFA0C, 784, 0x1_0F9C)

        # MOVE EXTERNAL FUNCTIONS
        new_loc = self.move_ext(0xB_FD1C, 14244, None)
        references = [  # internal references to external functions
            0x00D330,
            0x00D310,
            0x00D308,
            0x00D338,
            0x00D348,
            0x00D360,
            0x00D368,
            0x00D388,
            0x00D358,
            0x00D320,
            0x00D350,
            0x00D380,
            0x00D378,
            0x00D318,
            0x00D390,
            0x00D370,
            0x00D340,
            0x00D398,
            0x00D328,
        ]
        for reference in references:
            self.internal.lookup(reference)

        references = [  # external references to external functions
            0xC_1174,
            0xC_313C,
            0xC_049C,
            0xC_1178,
            0xC_220C,
            0xC_3490,
            0xC_3498,
        ]
        for reference in references:
            reference = reference - 0xB_FD1C + new_loc
            try:
                self.internal.lookup(reference)
            except (IndexError, KeyError):
                self.external.lookup(reference)

        # BALL sound samples.
        self.move_to_compressed_memory(0xC34C0, 6168, 0x43EC)
        self.rwdata_lookup(0xC34C0, 6168)
        self.move_to_compressed_memory(0xC4CD8, 2984, 0x459C)
        self.move_to_compressed_memory(0xC5880, 120, 0x4594)

        total_image_length = 193_568
        references = [
            0x1097C,
            0x1097C + 4,
            0x1097C + 8,
            0x1097C + 12,
            0x1097C + 16,
        ]
        if self.args.no_sleep_images:
            # Images Notes:
            #    * In-between images are just zeros.
            #
            # start: 0x900C_58F8   end: 0x900C_D83F    mario sleeping
            # start: 0x900C_D858   end: 0x900D_6C65    mario juggling
            # start: 0x900D_6C78   end: 0x900E_16E2    bowser sleeping
            # start: 0x900E_16F8   end: 0x900E_C301    mario and luigi eating pizza
            # start: 0x900E_C318   end: 0x900F_4D04    minions sleeping
            #          zero_padded_end: 0x900f_4d18
            # Total Image Length: 193_568 bytes
            printe("Deleting sleeping images.")
            self.external.replace(0xC58F8, b"\x00" * total_image_length)
            for reference in references:
                self.internal.replace(reference, b"\x00" * 4)  # Erase image references
            self.ext_offset -= total_image_length
        else:
            self.move_ext(0xC58F8, total_image_length, references)

        # Definitely at least contains part of the TIME graphic on startup screen.
        self.move_to_compressed_memory(0xF4D18, 2880, 0x10960)

        # What is this data?
        # The memcpy to this address is all zero, so i guess its not used?
        self.external.replace(0xF5858, b"\x00" * 34728)  # refence at internal 0x7210
        self.ext_offset -= 34728

        if self.compressed_memory_pos:
            # Compress and copy over compressed_memory
            self.internal.rwdata.append(
                self.compressed_memory[: self.compressed_memory_pos].copy(),
                self.compressed_memory.FLASH_BASE,
            )

        # Compress, insert, and reference the modified rwdata
        self.int_pos += self.internal.rwdata.write_table_and_data(
            0x17DB4, data_offset=self.int_pos
        )

        # Shorten the external firmware
        # This rounds the negative self.ext_offset towards zero.
        self.ext_offset = round_up_page(self.ext_offset)

        if self.args.no_save:
            # Disable nvram loading
            for nop in [0x495E, 0x49A6, 0x49B2]:
                self.internal.nop(nop, 2)
            # self.internal.b(0x4988, 0x49be)  # If you still want the first-startup "Press TIME Button" screen
            self.internal.b(0x4988, 0x49C0)  # Skips Press TIME Button screen

            # Disable nvram saving
            # This just skips the body of the nvram_write_bank function
            self.internal.b(0x48BE, 0x4912)

            self.ext_offset -= 8192
        else:
            printi("Update NVRAM read addresses")
            self.internal.asm(
                0x4856,
                "ite ne; "
                f"movne.w r4, #{hex(0xff000 + self.ext_offset)}; "
                f"moveq.w r4, #{hex(0xfe000 + self.ext_offset)}",
            )
            printi("Update NVRAM write addresses")
            self.internal.asm(
                0x48C0,
                "ite ne; "
                f"movne.w r4, #{hex(0xff000 + self.ext_offset)}; "
                f"moveq.w r4, #{hex(0xfe000 + self.ext_offset)}",
            )

        # Finally, shorten the firmware
        printi("Updating end of OTFDEC pointer")
        self.internal.add(0x1_06EC, self.ext_offset)
        self.external.shorten(self.ext_offset)

        internal_remaining_free = len(self.internal) - self.int_pos
        compressed_memory_free = (
            len(self.compressed_memory) - self.compressed_memory_pos
        )

        return internal_remaining_free, compressed_memory_free
