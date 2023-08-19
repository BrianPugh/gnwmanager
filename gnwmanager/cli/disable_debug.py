def disable_debug():
    """Disable the microcontroller's debug block."""
    from .main import session

    target = session.target

    target.write32(0xE00E1004, 0x00000000)
