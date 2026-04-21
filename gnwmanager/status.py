flashapp_status_enum_to_str = {
    0x00000000: "BOOTING",
    0xBAD00001: "BAD_HASH_RAM",
    0xBAD00002: "BAD_HASH_FLASH",
    0xBAD00003: "NOT_ALIGNED",
    0xBAD00004: "BAD_DECOMPRESS",
    0xBAD00005: "BAD_SEGFAULT",
    0xBAD00006: "BAD_FLASH_COMM",
    0xBAD00007: "BAD_SD_FS_MOUNT",
    0xBAD00008: "BAD_SD_OPEN",
    0xBAD00009: "BAD_SD_WRITE",
    0xBAD0000A: "BAD_SD_UNLINK",
    0xBAD0000B: "BAD_SD_DIR",
    0xBAD0000C: "BAD_SD_LIST_TRUNC",
    0xBAD0000D: "BAD_SD_READ",
    0xCAFE0000: "IDLE",
    0xCAFE0001: "ERASE",
    0xCAFE0002: "PROG",
    0xCAFE0003: "HASH",
}

flashapp_status_str_to_enum = {v: k for k, v in flashapp_status_enum_to_str.items()}
