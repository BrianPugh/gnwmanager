def disable_debug():
    """Disable the microcontroller's debug block."""
    from .main import gnw

    gnw.write_uint32(0xE00E1004, 0x00000000)
