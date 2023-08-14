#pragma once

typedef enum { // For signaling program status to computer
    FLASHAPP_BOOTING = 0,

    FLASHAPP_STATUS_BAD_HASH_RAM    = 0xbad00001,
    FLASHAPP_STATUS_BAD_HAS_FLASH   = 0xbad00002,
    FLASHAPP_STATUS_NOT_ALIGNED     = 0xbad00003,

    FLASHAPP_STATUS_IDLE            = 0xcafe0000,
    FLASHAPP_STATUS_DECOMPRESS      = 0xcafe0000,
    FLASHAPP_STATUS_ERASE           = 0xcafe0001,
    FLASHAPP_STATUS_PROG            = 0xcafe0002,
} flashapp_status_t;

void flashapp_main(void);
