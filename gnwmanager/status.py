flashapp_status_enum_to_str = {
    0: "BOOTING",
    0xBAD00001: "BAD_HASH_RAM",
    0xBAD00002: "BAD_HAS_FLASH",
    0xBAD00003: "NOT_ALIGNED",
    0xCAFE0000: "IDLE",
    0xCAFE0001: "DONE",
    0xCAFE0002: "BUSY",
}

flashapp_status_str_to_enum = {v: k for k, v in flashapp_status_enum_to_str.items()}
