#pragma once
#include <stdint.h>

enum gnwmanager_status { // For signaling program status to computer
    FLASHAPP_BOOTING = 0,

    FLASHAPP_STATUS_BAD_HASH_RAM    = 0xbad00001,
    FLASHAPP_STATUS_BAD_HASH_FLASH   = 0xbad00002,
    FLASHAPP_STATUS_NOT_ALIGNED     = 0xbad00003,
    FLASHAPP_STATUS_BAD_DECOMPRESS  = 0xbad00004,

    FLASHAPP_STATUS_IDLE            = 0xcafe0000,
    FLASHAPP_STATUS_ERASE     ,
    FLASHAPP_STATUS_PROG      ,
    FLASHAPP_STATUS_HASH      ,
};
typedef uint32_t gnwmanager_status_t;  // All computer interactions are uint32_t for simplicity.
                                    // No need to be stingy about RAM.

void gnwmanager_main(void);
