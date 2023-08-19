def validate_extflash_offset(val):
    if val >= 0x9000_0000:
        raise ValueError(f"Provided extflash offset 0x{val:08X}, did you mean 0x{(val - 0x9000_0000):08X} ?")
    if val % 4096 != 0:
        raise ValueError("Extflash offset must be a multiple of 4096.")


def validate_intflash_offset(val):
    if val >= 0x8100_0000:
        raise ValueError(f"Provided extflash offset 0x{val:08X}, did you mean 0x{(val - 0x8100_0000):08X} ?")
    if val >= 0x8000_0000:
        raise ValueError(f"Provided extflash offset 0x{val:08X}, did you mean 0x{(val - 0x8000_0000):08X} ?")
    if val % 8192 != 0:
        raise ValueError("Extflash offset must be a multiple of 8192.")
