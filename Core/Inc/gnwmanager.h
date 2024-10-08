#pragma once
#include <stdint.h>

enum gnwmanager_status { // For signaling program status to computer
    GNWMANAGER_BOOTING = 0,

    GNWMANAGER_STATUS_BAD_HASH_RAM    = 0xbad00001,
    GNWMANAGER_STATUS_BAD_HASH_FLASH   = 0xbad00002,
    GNWMANAGER_STATUS_NOT_ALIGNED     = 0xbad00003,
    GNWMANAGER_STATUS_BAD_DECOMPRESS  = 0xbad00004,
    GNWMANAGER_STATUS_BAD_SEGFAULT   = 0xbad00005,
    GNWMANAGER_STATUS_BAD_FLASH_COMM   = 0xbad00006,
    GNWMANAGER_STATUS_BAD_SD_FS_MOUNT = 0xbad00007,
    GNWMANAGER_STATUS_BAD_SD_OPEN     = 0xbad00008,
    GNWMANAGER_STATUS_BAD_SD_WRITE    = 0xbad00009,

    GNWMANAGER_STATUS_IDLE            = 0xcafe0000,
    GNWMANAGER_STATUS_ERASE     ,
    GNWMANAGER_STATUS_PROG      ,
    GNWMANAGER_STATUS_HASH      ,
};

typedef uint32_t gnwmanager_status_t;  // All computer interactions are uint32_t for simplicity.
                                    // No need to be stingy about RAM.

void gnwmanager_main(gnwmanager_status_t status);
void gnwmanager_set_status(gnwmanager_status_t status);
