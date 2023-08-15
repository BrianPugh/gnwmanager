#pragma once
#include <stdint.h>

enum flashapp_status { // For signaling program status to computer
    FLASHAPP_BOOTING = 0,

    FLASHAPP_STATUS_BAD_HASH_RAM    = 0xbad00001,
    FLASHAPP_STATUS_BAD_HAS_FLASH   = 0xbad00002,
    FLASHAPP_STATUS_NOT_ALIGNED     = 0xbad00003,
    FLASHAPP_STATUS_BAD_DECOMPRESS  = 0xbad00004,

    FLASHAPP_STATUS_IDLE            = 0xcafe0000,
    FLASHAPP_STATUS_DECOMPRESS,
    FLASHAPP_STATUS_ERASE     ,
    FLASHAPP_STATUS_PROG      ,
};
typedef uint32_t flashapp_status_t;  // All computer interactions are uint32_t for simplicity.
                                    // No need to be stingy about RAM.

void flashapp_main(void);
