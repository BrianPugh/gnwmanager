#include <assert.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "flash.h"
#include "sdcard.h"
#include "lcd.h"
#include "main.h"
#include "lzma.h"
#include "rg_rtc.h"
#include "gnwmanager.h"
#include "gnwmanager_gui.h"
#include "buttons.h"

#include "ff.h"


typedef enum {  // For the gnwmanager state machine
    GNWMANAGER_IDLE                   ,
    GNWMANAGER_DECOMPRESSING          ,
    GNWMANAGER_CHECK_HASH_RAM         ,
    GNWMANAGER_ERASE                  ,
    GNWMANAGER_ERASE_FINISH           ,
    GNWMANAGER_PROGRAM                ,
    GNWMANAGER_CHECK_HASH_FLASH       ,
    GNWMANAGER_IDLE_SD                ,
    GNWMANAGER_DECOMPRESSING_SD       ,
    GNWMANAGER_CHECK_HASH_RAM_SD      ,
    GNWMANAGER_PROGRAM_SD             ,
    GNWMANAGER_HASH_RETRY_WAIT        ,  // Wait for host to re-transmit a buffer after BAD_HASH_RAM_COMPRESSED

    GNWMANAGER_ERROR = 0xF000,
} gnwmanager_state_t;


enum gnwmanager_action {
    GNWMANAGER_ACTION_ERASE_AND_FLASH = 0,
    GNWMANAGER_ACTION_HASH = 1,
    GNWMANAGER_ACTION_WRITE_FILE_TO_SD = 2,
    GNWMANAGER_ACTION_LIST_SD_DIR = 3,
    GNWMANAGER_ACTION_DELETE_FILE_FROM_SD = 4,
    GNWMANAGER_ACTION_READ_FILE_FROM_SD = 5,
    GNWMANAGER_ACTION_SCAN_LFS = 6,
    GNWMANAGER_ACTION_SCAN_GEOMETRY = 7,
};

typedef struct {
    uint32_t address;
    uint32_t size;
    char type[16];
} gnwmanager_partition_t;


typedef struct {
    union{
        struct{
            volatile unsigned char *buffer;  // Computer <-> GnW data buffer

            // Number of bytes to program in the flash
            uint32_t size;

            // Where to program in the flash
            // offset into flash, not an absolute address 0x9XXX_XXXX
            uint32_t offset;

            // Whether or not an erase should be performed
            uint32_t erase;

            // Number of bytes to be erased from `offset`
            int32_t erase_bytes;

            // Set to 0 for no-compression
            uint32_t compressed_size;

            // The expected sha256 of the decompressed binary
            uint8_t expected_sha256[32];

            // 0 - ext; 1 - bank1; 2 - bank2
            uint32_t bank;

            // see enum gnwmanager_action
            uint32_t action;

            // Action was performed, computer should read back buffer now.
            uint32_t response_ready;

            // File path if write to filesystem
            uint8_t file_path[256];

            // current block for file
            uint32_t block;

            // total blocks for file
            uint32_t total_blocks;

            // sha256 of the bytes the host placed in `buffer`. All-zero = skip check.
            uint8_t compressed_sha256[32];

            /* Add future variables here */

            // This work context is ready for the on-device gnwmanager to process.
            // Place "ready" at the end of the struct so it's the last to be erased
            uint32_t ready;
        };
        struct{
            // Force spacing, allowing for backward-compatible additional variables
            char padding[1024];
        };
    };
} volatile work_context_t;

struct gnwmanager_comm {  // Values are read or written by the debugger
                        // only add attributes at the end (before work_buffers)
                        // so that addresses don't change.
    union {
        volatile struct{
            // output: Status register
            uint32_t status;

            // input: override status (only impacts GUI)
            uint32_t status_override;

            // input: if 0, RTC is not updated.
            uint32_t utc_timestamp;

            // input: In range [0, 26]
            uint32_t progress;

            // output: external flash size in bytes
            uint32_t flash_size;

            // output: minimum external flash erase size in bytes
            uint32_t min_erase_size;

            uint32_t upload_in_progress;  // computer -> device

            uint32_t download_in_progress;  // device -> computer

            uint8_t expected_hash[32];

            uint8_t actual_hash[32];

            // Retry handshake: when the device detects BAD_HASH_RAM_COMPRESSED it
            // writes the failed context index here, transitions to HASH_RETRY_WAIT,
            // and waits for the host to (a) re-transmit the data into the same
            // context buffer and (b) bump retry_request. The device then echoes
            // retry_request into retry_ack and re-runs the hash check.
            uint32_t failed_context_idx;  // output: which comm.buffer[i] needs re-transmit
            uint32_t retry_request;       // input: host increments to request a retry
            uint32_t retry_ack;           // output: device echoes after consuming retry_request
        };
        struct {
            // Force spacing, allowing for backward-compatible additional variables
            char padding[1024];
        };
    };

    volatile work_context_t contexts[2];

    work_context_t active_context;  // Working copy of context we are working on.

    volatile unsigned char buffer[2][256 << 10];

    unsigned char decompress_buffer[256 << 10];
};

static struct gnwmanager_comm comm __attribute__((section (".gnwmanager_comm")));

static FATFS FatFs;  // Fatfs handle
static FIL file; // File handle

void sdcard_hw_detect() {
    FRESULT cause;

    // Check if SD Card is connected to SPI1
    sdcard_init_spi1();
    sdcard_hw = GNWMANAGER_SDCARD_HW_1;
    cause = f_mount(&FatFs, (const TCHAR *)"", 1);
    if (cause == FR_OK) {
        f_mount(NULL, "", 0);
        return;
    } else {
        sdcard_deinit_spi1();
    }

    // Check if SD Card is connected over OSPI1
    sdcard_init_ospi1();
    sdcard_hw = GNWMANAGER_SDCARD_HW_2;
    cause = f_mount(&FatFs, (const TCHAR *)"", 1);
    if (cause == FR_OK) {
        f_mount(NULL, "", 0);
        return;
    } else {
        sdcard_deinit_ospi1();
    }

    // No SD Card detected
    sdcard_hw = GNWMANAGER_SDCARD_HW_NO_SD_FOUND;
}

/**
 * @param bank - Must be 1 or 2.
 * @param offset - Must be a multiple of 8192
 * @param bytes_remaining - Must be a multiple of 8192
 */
uint32_t erase_intflash(uint8_t bank, uint32_t offset, uint32_t size){
    static FLASH_EraseInitTypeDef EraseInitStruct;
    uint32_t PAGEError;

    assert(bank == 1 || bank == 2);
    assert((offset & 0x1fff) == 0);
    assert((size & 0x1fff) == 0);

    HAL_FLASH_Unlock();

    EraseInitStruct.TypeErase = FLASH_TYPEERASE_SECTORS;
    EraseInitStruct.Banks = bank;  // Must be 1 or 2
    EraseInitStruct.Sector = offset >> 13;
    EraseInitStruct.NbSectors = size >> 13;

    if (HAL_FLASHEx_Erase(&EraseInitStruct, &PAGEError) != HAL_OK) {
        Error_Handler();
    }

    HAL_FLASH_Lock();

    return 0;
}

static void sha256bank(uint8_t bank, uint8_t *digest, uint32_t offset, uint32_t size){
    OSPI_EnableMemoryMappedMode();

    uint32_t base_address;
    if(bank == 0){
        base_address = 0x90000000;
    }
    else if(bank == 1){
        base_address = 0x08000000;
    }
    else if(bank == 2){
        base_address = 0x08100000;
    }
    else{
        assert(0);
    }

    if(HAL_HASHEx_SHA256_Start(&hhash,
                (uint8_t *)(base_address + offset), size,
                digest,
                HAL_MAX_DELAY
            )){
        Error_Handler();
    }

}

static uint32_t context_counter = 1;


static work_context_t *get_context(){
    for(uint8_t i=0; i < 2; i++){
        if(comm.contexts[i].ready == context_counter){
            comm.contexts[i].buffer = comm.buffer[i];
            return &comm.contexts[i];
        }
    }
    return NULL;
}

static void release_context(work_context_t *context){
    memset((void *)context, 0, sizeof(work_context_t));
}

bool gnwmanager_is_idle(void){
    return comm.status == GNWMANAGER_STATUS_IDLE
        && comm.contexts[0].ready == 0
        && comm.contexts[1].ready == 0
        && !comm.upload_in_progress
        && !comm.download_in_progress;
}

void gnwmanager_set_status(gnwmanager_status_t status){
    static gnwmanager_status_t prev_status = 0;
    comm.status = status;
    if(status != prev_status){
        gnwmanager_gui_draw();
    }
    prev_status = status;
}

/**
 * Compute sha256 hashes of 256KB chunks.
 */
static void gnwmanager_action_hash(work_context_t *context){
    OSPI_EnableMemoryMappedMode();
    const uint32_t chunk_size = 256 << 10;
    uint8_t *response_buffer = (uint8_t *) context->buffer;
    uint32_t offset_end = context->offset + context->size;
    for(uint32_t offset=context->offset; offset < offset_end; offset += chunk_size){
        // Each iteration is expected to take around
        wdog_refresh();
        gnwmanager_gui_draw();
        uint32_t remaining_bytes = (offset_end - offset);
        uint32_t size = chunk_size < remaining_bytes ? chunk_size : remaining_bytes;
        sha256bank(0, response_buffer, offset, size);
        response_buffer += 32;
    }
    context->response_ready = 1;
}

static void gnwmanager_action_list_sd_dir(work_context_t *context){
    FRESULT res;
    DIR dir;
    FILINFO fno;
    uint8_t *out = (uint8_t *)context->buffer;
    const uint32_t cap = 256u << 10;
    uint32_t used = 0;

    if (sdcard_hw == GNWMANAGER_SDCARD_HW_UNDETECTED) {
        sdcard_hw_detect();
    }
    if (sdcard_hw < GNWMANAGER_SDCARD_HW_1) {
        gnwmanager_set_status(GNWMANAGER_STATUS_BAD_SD_FS_MOUNT);
        context->size = 0;
        context->response_ready = 1;
        return;
    }

    f_mount(&FatFs, (const TCHAR *)"", 1);
    res = f_opendir(&dir, (const TCHAR *)context->file_path);
    if (res != FR_OK) {
        gnwmanager_set_status(GNWMANAGER_STATUS_BAD_SD_DIR);
        f_mount(NULL, "", 0);
        context->size = 0;
        context->response_ready = 1;
        return;
    }

    for (;;) {
        res = f_readdir(&dir, &fno);
        if (res != FR_OK || fno.fname[0] == 0) {
            break;
        }
        const char *name = fno.fname;
        if (name[0] == '.' && name[1] == 0) {
            continue;
        }
        if (name[0] == '.' && name[1] == '.' && name[2] == 0) {
            continue;
        }
        // Inlined "%s%s\n" formatting — keeps the entire newlib nano-vfprintf
        // stack out of the firmware (~1.7KB saved).
        const uint32_t name_len = (uint32_t)strlen(name);
        const uint32_t suffix_len = (fno.fattrib & AM_DIR) ? 2u : 1u;  // '/'+'\n' or just '\n'
        if (name_len + suffix_len > cap - used) {
            gnwmanager_set_status(GNWMANAGER_STATUS_BAD_SD_LIST_TRUNC);
            f_closedir(&dir);
            f_mount(NULL, "", 0);
            context->size = used;
            context->response_ready = 1;
            return;
        }
        memcpy(out + used, name, name_len);
        used += name_len;
        if (fno.fattrib & AM_DIR) {
            out[used++] = '/';
        }
        out[used++] = '\n';
    }

    f_closedir(&dir);
    f_mount(NULL, "", 0);
    gnwmanager_set_status(GNWMANAGER_STATUS_IDLE);
    context->size = used;
    context->response_ready = 1;
}

static void gnwmanager_action_delete_sd_file(work_context_t *context){
    if (sdcard_hw == GNWMANAGER_SDCARD_HW_UNDETECTED) {
        sdcard_hw_detect();
    }
    if (sdcard_hw < GNWMANAGER_SDCARD_HW_1) {
        gnwmanager_set_status(GNWMANAGER_STATUS_BAD_SD_FS_MOUNT);
        context->response_ready = 1;
        return;
    }

    f_mount(&FatFs, (const TCHAR *)"", 1);
    FRESULT res = f_unlink((const TCHAR *)context->file_path);
    f_mount(NULL, "", 0);

    if (res != FR_OK) {
        gnwmanager_set_status(GNWMANAGER_STATUS_BAD_SD_UNLINK);
    } else {
        gnwmanager_set_status(GNWMANAGER_STATUS_IDLE);
    }
    context->response_ready = 1;
}

static void gnwmanager_action_read_sd_file(work_context_t *context){
    FRESULT res;
    UINT br = 0;
    uint32_t want;

    if (sdcard_hw == GNWMANAGER_SDCARD_HW_UNDETECTED) {
        sdcard_hw_detect();
    }
    if (sdcard_hw < GNWMANAGER_SDCARD_HW_1) {
        gnwmanager_set_status(GNWMANAGER_STATUS_BAD_SD_FS_MOUNT);
        context->size = 0;
        context->response_ready = 1;
        return;
    }

    f_mount(&FatFs, (const TCHAR *)"", 1);
    res = f_open(&file, (const TCHAR *)context->file_path, FA_READ);
    if (res != FR_OK) {
        gnwmanager_set_status(GNWMANAGER_STATUS_BAD_SD_OPEN);
        f_mount(NULL, "", 0);
        context->size = 0;
        context->response_ready = 1;
        return;
    }

    /* size==0 and offset==0: return file length in context->size (host progress). */
    if (context->size == 0) {
        if (context->offset != 0) {
            gnwmanager_set_status(GNWMANAGER_STATUS_BAD_SD_READ);
            f_close(&file);
            f_mount(NULL, "", 0);
            context->size = 0;
            context->response_ready = 1;
            return;
        }
        FSIZE_t fsz = f_size(&file);
        f_close(&file);
        f_mount(NULL, "", 0);
        gnwmanager_set_status(GNWMANAGER_STATUS_IDLE);
        context->size = (fsz > (FSIZE_t)0xffffffffu) ? 0xffffffffu : (uint32_t)fsz;
        context->response_ready = 1;
        return;
    }

    want = context->size;
    if (want > (256u << 10)) {
        want = 256u << 10;
    }

    if (context->offset) {
        res = f_lseek(&file, (FSIZE_t)context->offset);
        if (res != FR_OK || f_tell(&file) != (FSIZE_t)context->offset) {
            gnwmanager_set_status(GNWMANAGER_STATUS_BAD_SD_READ);
            f_close(&file);
            f_mount(NULL, "", 0);
            context->size = 0;
            context->response_ready = 1;
            return;
        }
    }

    res = f_read(&file, (void *)context->buffer, want, &br);
    f_close(&file);
    f_mount(NULL, "", 0);

    if (res != FR_OK) {
        gnwmanager_set_status(GNWMANAGER_STATUS_BAD_SD_READ);
        context->size = 0;
        context->response_ready = 1;
        return;
    }

    gnwmanager_set_status(GNWMANAGER_STATUS_IDLE);
    context->size = br;
    context->response_ready = 1;
}

static inline bool safe_memcmp(volatile const uint8_t *p1, const uint8_t *p2, size_t len) {
    for (size_t i = 0; i < len; i++) {
        if (p1[i] != p2[i]) return false;
    }
    return true;
}

static bool is_lfs_superblock(uint32_t addr, uint32_t flash_size) {
    if (addr < 0x90000000 || addr + 32 > 0x90000000 + flash_size) return false;
    volatile const uint8_t *block = (volatile const uint8_t *)addr;
    if (!safe_memcmp(block + 8, (const uint8_t *)"littlefs", 8)) return false;
    uint32_t version = block[20] | (block[21] << 8) | (block[22] << 16) | (block[23] << 24);
    uint32_t block_size = block[24] | (block[25] << 8) | (block[26] << 16) | (block[27] << 24);
    uint32_t block_count = block[28] | (block[29] << 8) | (block[30] << 16) | (block[31] << 24);
    return ((version >> 16) == 2 && block_size >= 128 && block_size <= 8192 && block_count > 0);
}

static void gnwmanager_action_scan_lfs(work_context_t *context) {
    OSPI_EnableMemoryMappedMode();
    uint32_t flash_size = OSPI_GetSize();
    uint32_t mib = 1024 * 1024;
    gnwmanager_partition_t *partitions = (gnwmanager_partition_t *)context->buffer;
    uint32_t count = 0;
    uint32_t max_count = (256 << 10) / sizeof(gnwmanager_partition_t);

    // Scan backwards at 1MiB boundaries
    for (uint32_t boundary = flash_size; boundary >= mib; boundary -= mib) {
        uint32_t sb_addr = 0x90000000 + boundary - 4096;
        if (is_lfs_superblock(sb_addr, flash_size)) {
            const uint8_t *block = (const uint8_t *)sb_addr;
            uint32_t block_size = block[24] | (block[25] << 8) | (block[26] << 16) | (block[27] << 24);
            uint32_t block_count = block[28] | (block[29] << 8) | (block[30] << 16) | (block[31] << 24);
            uint32_t p_size = block_size * block_count;

            if (p_size > 0 && block_size > 0 && p_size <= flash_size && boundary >= p_size) {
                uint32_t p_start = boundary - p_size;
                if (p_start + p_size <= flash_size && (p_start % 4096 == 0)) {
                    if (count < max_count) {
                        partitions[count].address = p_start;
                        partitions[count].size = p_size;
                        strcpy(partitions[count].type, "LittleFS");
                        count++;
                    }
                }
            }
        }
    }
    context->size = count * sizeof(gnwmanager_partition_t);
    context->response_ready = 1;
}

static void gnwmanager_action_scan_geometry(work_context_t *context) {
    OSPI_EnableMemoryMappedMode();
    uint32_t flash_size = OSPI_GetSize();
    gnwmanager_partition_t *partitions = (gnwmanager_partition_t *)context->buffer;
    uint32_t count = 0;
    uint32_t max_count = (256 << 10) / sizeof(gnwmanager_partition_t);

    static const uint8_t mario_int_sig[] = {0x30, 0x13, 0x01, 0x20};
    static const uint8_t zelda_int_sig[] = {0x20, 0xb6, 0x01, 0x20};
    static const uint8_t zelda_stock_sig[] = {0x3C, 0x13, 0x96, 0xC5, 0x79, 0x38, 0x71, 0xD6};
    static const uint8_t zelda_patched_sig[] = {0x22, 0x21, 0x23, 0x22, 0x22, 0x22, 0x22, 0x22};
    static const uint8_t mario_stock_sig[] = {0xFE, 0x6E, 0xF8, 0x01, 0x30, 0x77, 0x2D, 0x3A};
    static const uint8_t mario_patched_sig[] = {0x78, 0xD8, 0xA9, 0x10, 0x8D, 0x00, 0x20, 0xA2};

    // 2. External Flash Check
    uint32_t strides[] = {1024 * 1024, 512 * 1024, 256 * 1024, 128 * 1024, 64 * 1024};

    for (int s = 0; s < 5; s++) {
        uint32_t stride = strides[s];
        for (uint32_t addr = 0; addr <= flash_size; addr += stride) {
            // Geometric skip: skip addresses already covered by a larger stride
            if (stride < 1024 * 1024 && (addr % (stride * 2) == 0)) continue;

            uint32_t phys_addr = addr;
            uint32_t mapped_addr = 0x90000000 + phys_addr;
            volatile const uint8_t *sector = (volatile const uint8_t *)mapped_addr;

            bool is_lfs = false;

            // LittleFS Check (Forward: superblock at phys_addr)
            if (is_lfs_superblock(mapped_addr, flash_size)) {
                is_lfs = true;
                uint32_t anchor_addr = phys_addr;
                if (phys_addr + 4096 + 32 <= flash_size && is_lfs_superblock(mapped_addr + 4096, flash_size)) {
                    anchor_addr = phys_addr + 4096;
                }

                volatile const uint8_t *block = (volatile const uint8_t *)(0x90000000 + anchor_addr);
                uint32_t bsize = block[24] | (block[25] << 8) | (block[26] << 16) | (block[27] << 24);
                uint32_t bcount = block[28] | (block[29] << 8) | (block[30] << 16) | (block[31] << 24);
                uint32_t p_size = bsize * bcount;
                if (p_size > 0 && bsize > 0 && p_size <= flash_size && anchor_addr + bsize >= p_size) {
                    uint32_t p_start = (anchor_addr + bsize) - p_size;
                    if (p_start + p_size <= flash_size && (p_start % 4096 == 0)) {
                        bool exists = false;
                        for (uint32_t i = 0; i < count; i++) {
                            if (p_start == partitions[i].address && p_size == partitions[i].size) {
                                exists = true; break;
                            }
                        }
                        if (!exists && count < max_count) {
                            partitions[count].address = p_start;
                            partitions[count].size = p_size;
                            strcpy(partitions[count].type, "LittleFS");
                            count++;
                        }
                    }
                }
            }
            // LittleFS Check (Inverted: superblock at phys_addr - 4096)
            else if (phys_addr >= 4096 && is_lfs_superblock(mapped_addr - 4096, flash_size)) {
                is_lfs = true;
                uint32_t anchor_addr = phys_addr - 4096;
                volatile const uint8_t *block = (volatile const uint8_t *)(0x90000000 + anchor_addr);
                uint32_t bsize = block[24] | (block[25] << 8) | (block[26] << 16) | (block[27] << 24);
                uint32_t bcount = block[28] | (block[29] << 8) | (block[30] << 16) | (block[31] << 24);
                uint32_t p_size = bsize * bcount;
                if (p_size > 0 && bsize > 0 && p_size <= flash_size && anchor_addr + bsize >= p_size) {
                    uint32_t p_start = (anchor_addr + bsize) - p_size;
                    if (p_start + p_size <= flash_size && (p_start % 4096 == 0)) {
                        bool exists = false;
                        for (uint32_t i = 0; i < count; i++) {
                            if (p_start == partitions[i].address && p_size == partitions[i].size) {
                                exists = true; break;
                            }
                        }
                        if (!exists && count < max_count) {
                            partitions[count].address = p_start;
                            partitions[count].size = p_size;
                            strcpy(partitions[count].type, "LittleFS");
                            count++;
                        }
                    }
                }
            }

            if (is_lfs) continue;

            // Coverage skip: skip addresses already identified as being inside a partition
            bool covered = false;
            for (uint32_t i = 0; i < count; i++) {
                if (addr >= partitions[i].address && addr < partitions[i].address + partitions[i].size) {
                    covered = true; break;
                }
            }
            if (covered) continue;
            // FAT Check
            else if (phys_addr + 512 <= flash_size && sector[510] == 0x55 && sector[511] == 0xAA && (sector[0] == 0xEB || sector[0] == 0xE9)) {
                uint32_t bps   = sector[0x0B] | (sector[0x0C] << 8);
                uint32_t tot16 = sector[0x13] | (sector[0x14] << 8);
                uint32_t tot32 = sector[0x20] | (sector[0x21] << 8) | (sector[0x22] << 16) | (sector[0x23] << 24);
                uint32_t total_sectors = tot16 ? tot16 : tot32;
                if (bps >= 512 && bps <= 4096 && total_sectors) {
                    uint32_t p_size = total_sectors * bps;
                    if (count < max_count) {
                        partitions[count].address = phys_addr;
                        partitions[count].size = p_size;
                        strcpy(partitions[count].type, "FAT");
                        count++;
                    }
                }
            }
            // FrogFS check
            else if (phys_addr + 12 <= flash_size && safe_memcmp(sector, (const uint8_t *)"FROG", 4)) {
                uint32_t bin_sz = sector[8] | (sector[9] << 8) | (sector[10] << 16) | (sector[11] << 24);
                if (count < max_count) {
                    partitions[count].address = phys_addr;
                    partitions[count].size = bin_sz;
                    strcpy(partitions[count].type, "FrogFS");
                    count++;
                }
            }
            // Internal Flash Backup Check
            else if (phys_addr + 131072 <= flash_size && (safe_memcmp(sector, mario_int_sig, 4) || safe_memcmp(sector, zelda_int_sig, 4))) {
                if (safe_memcmp(sector, mario_int_sig, 4)) {
                    if (count < max_count) {
                        partitions[count].address = phys_addr;
                        partitions[count].size = 131072;
                        if (sector[131071] == 0xFF) {
                            strcpy(partitions[count].type, "Mario OFW (Int)");
                        } else {
                            strcpy(partitions[count].type, "Mario Pat(Int)");
                        }
                        count++;
                    }
                }
                else if (safe_memcmp(sector, zelda_int_sig, 4)) {
                    if (count < max_count) {
                        partitions[count].address = phys_addr;
                        partitions[count].size = 131072;
                        if (sector[131071] == 0xFF) {
                            strcpy(partitions[count].type, "Zelda OFW (Int)");
                        } else {
                            strcpy(partitions[count].type, "Zelda Pat(Int)");
                        }
                        count++;
                    }
                }
            }
            // Asset Blobs Check
            else if (phys_addr + 8 <= flash_size) {
                if (safe_memcmp(sector, zelda_stock_sig, 8)) {
                    if (count < max_count && phys_addr + 4 * 1024 * 1024 <= flash_size) {
                        partitions[count].address = phys_addr;
                        partitions[count].size = 4 * 1024 * 1024;
                        strcpy(partitions[count].type, "Zelda OFW");
                        count++;
                    }
                }
                else if (safe_memcmp(sector, zelda_patched_sig, 8)) {
                    if (count < max_count && phys_addr >= 0x20000 && (phys_addr - 0x20000 + 4 * 1024 * 1024 <= flash_size)) {
                        partitions[count].address = phys_addr - 0x20000;
                        partitions[count].size = 4 * 1024 * 1024;
                        strcpy(partitions[count].type, "Zelda Assets");
                        count++;
                    }
                }
                else if (safe_memcmp(sector, mario_stock_sig, 8)) {
                    if (count < max_count && phys_addr + 1 * 1024 * 1024 <= flash_size) {
                        partitions[count].address = phys_addr;
                        partitions[count].size = 1 * 1024 * 1024;
                        strcpy(partitions[count].type, "Mario OFW");
                        count++;
                    }
                }
                else if (safe_memcmp(sector, mario_patched_sig, 8)) {
                    if (count < max_count && phys_addr + 1 * 1024 * 1024 <= flash_size) {
                        partitions[count].address = phys_addr;
                        partitions[count].size = 1 * 1024 * 1024;
                        strcpy(partitions[count].type, "Mario Assets");
                        count++;
                    }
                }
            }
        }
    }
    context->size = count * sizeof(gnwmanager_partition_t);
    context->response_ready = 1;
}

static bool ext_is_erased(uint32_t offset, uint32_t size){
    OSPI_EnableMemoryMappedMode();
    uint32_t *end = (uint32_t *)(0x90000000 + offset + size);
    for(uint32_t *ptr = (uint32_t *)(0x90000000 + offset); ptr < end; ptr++){
        if(*ptr != 0xFFFFFFFF){
            return false;
        }
    }
    return true;
}

static void gnwmanager_run(void)
{
    static gnwmanager_state_t state = GNWMANAGER_IDLE;
    static uint32_t erase_offset = 0;  // Holds intermediate erase address.
                                        // Is it's own variable since context->offset is used by both
                                        // programming and erasing.
    static uint32_t erase_bytes_left = 0;
    static uint32_t program_offset = 0; // Current offset into extflash that needs to be programmed
    static uint32_t program_bytes_remaining = 0;
    static work_context_t *source_context;

    work_context_t *working_context = &comm.active_context;
    uint8_t program_calculated_sha256[32];

    wdog_refresh();
    gnwmanager_gui_draw();

    switch (state) {
    case GNWMANAGER_IDLE:
        OSPI_EnableMemoryMappedMode();

        if(comm.utc_timestamp){
            // Set time
            GW_SetUnixTime(comm.utc_timestamp);
            comm.utc_timestamp = 0;
        }

        // Attempt to find the next ready working_context in queue
        if((source_context = get_context()) == NULL){
            /* Do not overwrite a BAD_* status while the host still holds ready!=0 on a
             * context (e.g. LIST_SD_DIR / DELETE_FILE_FROM_SD / HASH returned early);
             * otherwise the next loop would set IDLE before the host reads the error. */
            uint32_t st = comm.status;
            uint8_t any_ready = (comm.contexts[0].ready != 0) || (comm.contexts[1].ready != 0);
            if ((st & 0xffff0000u) == 0xbad00000u) {
                if (!any_ready) {
                    gnwmanager_set_status(GNWMANAGER_STATUS_IDLE);
                }
            } else {
                gnwmanager_set_status(GNWMANAGER_STATUS_IDLE);
            }
            break;
        }
        context_counter++;

        /* Clear a stale BAD_* from a prior failure before handling this command. */
        if ((comm.status & 0xffff0000u) == 0xbad00000u) {
            gnwmanager_set_status(GNWMANAGER_STATUS_IDLE);
        }

        switch(source_context->action){
            case GNWMANAGER_ACTION_ERASE_AND_FLASH:
                // The rest of this function
                break;
            case GNWMANAGER_ACTION_HASH:
                gnwmanager_set_status(GNWMANAGER_STATUS_HASH);
                gnwmanager_action_hash(source_context);
                return;
            case GNWMANAGER_ACTION_LIST_SD_DIR:
                gnwmanager_set_status(GNWMANAGER_STATUS_PROG);
                gnwmanager_action_list_sd_dir(source_context);
                return;
            case GNWMANAGER_ACTION_DELETE_FILE_FROM_SD:
                gnwmanager_set_status(GNWMANAGER_STATUS_PROG);
                gnwmanager_action_delete_sd_file(source_context);
                return;
            case GNWMANAGER_ACTION_READ_FILE_FROM_SD:
                gnwmanager_set_status(GNWMANAGER_STATUS_PROG);
                gnwmanager_action_read_sd_file(source_context);
                return;
            case GNWMANAGER_ACTION_SCAN_LFS:
                gnwmanager_set_status(GNWMANAGER_STATUS_PROG);
                gnwmanager_action_scan_lfs(source_context);
                return;
            case GNWMANAGER_ACTION_SCAN_GEOMETRY:
                gnwmanager_set_status(GNWMANAGER_STATUS_PROG);
                gnwmanager_action_scan_geometry(source_context);
                return;
            case GNWMANAGER_ACTION_WRITE_FILE_TO_SD:
                state = GNWMANAGER_IDLE_SD;
                if (sdcard_hw == GNWMANAGER_SDCARD_HW_UNDETECTED) {
                    sdcard_hw_detect();
                }
                if (sdcard_hw < GNWMANAGER_SDCARD_HW_1) {
                    gnwmanager_set_status(GNWMANAGER_STATUS_BAD_SD_FS_MOUNT);
                    release_context(source_context);
                    state = GNWMANAGER_ERROR;
                    return;
                }
        }

        // Copy the context data into the active working_context
        memcpy((void *)working_context, (void *)source_context, sizeof(work_context_t));

        program_offset = working_context->offset;
        program_bytes_remaining = working_context->size;

        if(working_context->bank){
            assert(working_context->bank == 1 || working_context->bank == 2);
            assert((working_context->offset & 0x1fff) == 0);
            assert((working_context->size & 0x1fff) == 0);
            program_offset += (working_context->bank == 1) ? 0x08000000 : 0x08100000;
        }

        if (state == GNWMANAGER_IDLE) {
            // Compute the hash to see if the programming operation would result in anything.
            if(working_context->size){
                gnwmanager_set_status(GNWMANAGER_STATUS_HASH);
                sha256bank(working_context->bank, program_calculated_sha256, working_context->offset, working_context->size);
                if (memcmp((char *)program_calculated_sha256, (char *)working_context->expected_sha256, 32) == 0) {
                    // Contents of this chunk didn't change. Skip & release working_context.
                    release_context(source_context);
                    break;
                }
            }

            // If we're erasing, check if we actually need to erase (skip if performing whole-chip erase)
            if(working_context->bank == 0 && working_context->erase_bytes && ext_is_erased(working_context->offset, working_context->erase_bytes)){
                working_context->erase = 0;
            }

            if(working_context->erase){
                gnwmanager_set_status(GNWMANAGER_STATUS_ERASE);
                if(working_context->bank == 0){
                    // Start a non-blocking flash erase to run in the background
                    erase_offset = working_context->offset;
                    erase_bytes_left = working_context->erase_bytes;

                    uint32_t smallest_erase = OSPI_GetSmallestEraseSize();
                    if (erase_offset & (smallest_erase - 1)) {
                        // Address not aligned to smallest erase size
                        gnwmanager_set_status(GNWMANAGER_STATUS_NOT_ALIGNED);
                        state = GNWMANAGER_ERROR;
                        break;
                    }
                    // Round size up to nearest erase size if needed ?
                    if ((erase_bytes_left & (smallest_erase - 1)) != 0) {
                        erase_bytes_left += smallest_erase - (erase_bytes_left & (smallest_erase - 1));
                    }
                    OSPI_DisableMemoryMappedMode();
                    OSPI_Erase(&erase_offset, &erase_bytes_left, false);
                }
            }
        }
        state++;
        break;
    case GNWMANAGER_IDLE_SD:
        return;
    case GNWMANAGER_DECOMPRESSING:
    case GNWMANAGER_DECOMPRESSING_SD:
        if(working_context->compressed_size){
            // If the host populated compressed_sha256, verify the compressed bytes
            // match before LZMA touches them, so a transfer/cache corruption surfaces
            // as BAD_HASH_RAM rather than the more confusing BAD_DECOMPRESS.
            // All-zero = host didn't populate; skip.
            uint8_t expected_or = 0;
            for(int k = 0; k < 32; k++){
                expected_or |= working_context->compressed_sha256[k];
            }
            if(expected_or){
                if(HAL_HASHEx_SHA256_Start(&hhash,
                    (uint8_t *)working_context->buffer, working_context->compressed_size,
                    program_calculated_sha256,
                    HAL_MAX_DELAY
                )){
                    Error_Handler();
                }
                if(memcmp((const void *)program_calculated_sha256,
                          (const void *)working_context->compressed_sha256, 32) != 0){
                    memcpy((void *)comm.actual_hash, program_calculated_sha256, 32);
                    memcpy((void *)comm.expected_hash,
                           (void *)working_context->compressed_sha256, 32);
                    /* Publish which comm.buffer[i] needs re-transmit BEFORE
                     * setting status: the host reads status first and uses
                     * failed_context_idx to drive the retry. source_context
                     * is still valid here — release_context() runs further
                     * down on the success path. */
                    comm.failed_context_idx = (uint32_t)(source_context - &comm.contexts[0]);
                    gnwmanager_set_status(GNWMANAGER_STATUS_BAD_HASH_RAM_COMPRESSED);
                    state = GNWMANAGER_HASH_RETRY_WAIT;
                    break;
                }
            }

            // Decompress the data; nothing after this state should reference decompression.
            uint32_t n_decomp_bytes;
            n_decomp_bytes = lzma_inflate(comm.decompress_buffer, sizeof(comm.decompress_buffer),
                                          (uint8_t *)working_context->buffer, working_context->compressed_size);
            if(n_decomp_bytes == 0 || n_decomp_bytes != working_context->size){
                gnwmanager_set_status(GNWMANAGER_STATUS_BAD_DECOMPRESS);
                state = GNWMANAGER_ERROR;
            }
        }
        else{
            //The data came in NOT compressed
            memcpy((void *)comm.decompress_buffer, (void *)working_context->buffer, working_context->size);
        }
        working_context->buffer = comm.decompress_buffer;
        // We can now early release the source_context
        release_context(source_context);
        state++;
        break;
    case GNWMANAGER_CHECK_HASH_RAM:
    case GNWMANAGER_CHECK_HASH_RAM_SD:
        // Calculate sha256 hash of the RAM first
        if(HAL_HASHEx_SHA256_Start(&hhash,
            (uint8_t *)working_context->buffer, working_context->size,
            program_calculated_sha256,
            HAL_MAX_DELAY
        )){
            Error_Handler();
        }

        if (memcmp((const void *)program_calculated_sha256, (const void *)working_context->expected_sha256, 32) != 0) {
            // Hashes don't match even in RAM, openocd loading failed.
            memcpy((void *)comm.actual_hash, program_calculated_sha256, 32);
            memcpy((void *)comm.expected_hash, (void *)working_context->expected_sha256, 32);
            gnwmanager_set_status(GNWMANAGER_STATUS_BAD_HASH_RAM);
            state = GNWMANAGER_ERROR;
            break;
        }
        state++;
        break;
    case GNWMANAGER_ERASE:
        OSPI_DisableMemoryMappedMode();
        if (!working_context->erase) {
            state = GNWMANAGER_PROGRAM;
            break;
        }
        gnwmanager_set_status(GNWMANAGER_STATUS_ERASE);

        if(working_context->bank == 0){
            // This body is usually called a few times
            if (working_context->erase_bytes == 0) {
                OSPI_ChipErase(false);
                state++;
            } else {
                // Returns true when all erasing has been complete.
                if (OSPI_Erase(&erase_offset, &erase_bytes_left, false)) {
                    state++;
                }
            }
        }
        else{
            // Erase an internal bank
            if (working_context->erase_bytes == 0) {
                working_context->erase_bytes = 256 << 10;
            }
            erase_intflash(working_context->bank, working_context->offset, working_context->erase_bytes);
            state++;
        }
        break;
    case GNWMANAGER_ERASE_FINISH:
        OSPI_DisableMemoryMappedMode();
        if(OSPI_ChipIdle()){  // Stay in state until flashchip is idle.
            state++;
        }
        break;
    case GNWMANAGER_PROGRAM_SD:
        if (sdcard_hw >= GNWMANAGER_SDCARD_HW_1) {
            gnwmanager_set_status(GNWMANAGER_STATUS_PROG);
            FRESULT res;
            UINT bytes_written;
            if (working_context->block == 0) {
                f_mount(&FatFs, (const TCHAR *)"", 1);
                // This is first block, open file
                res = f_open(&file, (const char *)working_context->file_path, FA_WRITE | FA_CREATE_ALWAYS);
                if (res != FR_OK) {
                    /* Unmount so the next attempt re-mounts cleanly; otherwise
                     * FATFS retains stale state from this failed open. */
                    f_mount(NULL, "", 0);
                    gnwmanager_set_status(GNWMANAGER_STATUS_BAD_SD_OPEN);
                    state = GNWMANAGER_ERROR;
                    break;
                }
            }
            if (working_context->size > 0) {
                res = f_write(&file, (const void *)working_context->buffer, working_context->size, &bytes_written);
                if (res != FR_OK || bytes_written < working_context->size) {
                    /* Close + unmount so the half-written file's directory entry
                     * is at least finalized, and the next sdpush starts from a
                     * clean FATFS/FIL state. */
                    f_close(&file);
                    f_mount(NULL, "", 0);
                    gnwmanager_set_status(GNWMANAGER_STATUS_BAD_SD_WRITE);
                    state = GNWMANAGER_ERROR;
                    break;
                }
            }
            if (working_context->block+1 == working_context->total_blocks) {
                f_close(&file);
                f_mount(NULL, "", 0);
            }
            state = GNWMANAGER_IDLE;
        } else {
            gnwmanager_set_status(GNWMANAGER_STATUS_BAD_SD_FS_MOUNT);
            state = GNWMANAGER_ERROR;
            break;
        }
        break;
    case GNWMANAGER_PROGRAM:
        OSPI_DisableMemoryMappedMode();
        gnwmanager_set_status(GNWMANAGER_STATUS_PROG);
        if (program_bytes_remaining == 0) {
            state++;
            break;
        }
        if(working_context->bank == 0){
            uint32_t dest_page = program_offset / 256;
            uint32_t bytes_to_write = program_bytes_remaining > 256 ? 256 : program_bytes_remaining;
            OSPI_NOR_WriteEnable();
            OSPI_PageProgram(dest_page * 256, (uint8_t *)working_context->buffer, bytes_to_write);
            program_offset += bytes_to_write;
            working_context->buffer += bytes_to_write;
            program_bytes_remaining -= bytes_to_write;
        }
        else{
            // Prog internal bank
            HAL_FLASH_Unlock();
            while(program_bytes_remaining){
                if (HAL_FLASH_Program(FLASH_TYPEPROGRAM_FLASHWORD, program_offset, (uint32_t)working_context->buffer) != HAL_OK) {
                    Error_Handler();
                }
                // A flash word is 128bits (16 bytes)
                program_offset += 16;
                working_context->buffer += 16;
                program_bytes_remaining -= 16;
            }
            HAL_FLASH_Lock();
            state++;
        }
        break;
    case GNWMANAGER_CHECK_HASH_FLASH:
        OSPI_EnableMemoryMappedMode();
        // Calculate sha256 hash of the FLASH.
        sha256bank(working_context->bank, program_calculated_sha256, working_context->offset, working_context->size);

        if (memcmp((char *)program_calculated_sha256, (char *)working_context->expected_sha256, 32) != 0) {
            // Hashes don't match in FLASH, programming failed.
            memcpy((void *)comm.actual_hash, program_calculated_sha256, 32);
            memcpy((void *)comm.expected_hash, (void *)working_context->expected_sha256, 32);
            gnwmanager_set_status(GNWMANAGER_STATUS_BAD_HASH_FLASH);
            state = GNWMANAGER_ERROR;
            break;
        }
        // Hash OK in FLASH
        state = GNWMANAGER_IDLE;
        break;
    case GNWMANAGER_HASH_RETRY_WAIT:
        /* Park until the host bumps retry_request. The host has by then
         * re-transmitted the source buffer (and compressed_sha256) into the
         * same comm.contexts[failed_context_idx] / comm.buffer[failed_context_idx].
         * Re-sync working_context from source_context and re-enter
         * DECOMPRESSING_* to re-run the compressed-hash check. */
        if (comm.retry_request != comm.retry_ack) {
            memcpy((void *)working_context, (void *)source_context, sizeof(work_context_t));
            /* Clear BAD status so the GUI doesn't get stuck showing the error
             * across retries. The host polls retry_ack to know the retry was
             * consumed, so update status first to ensure that when the host
             * sees retry_ack == retry_request, the post-retry status is
             * already visible (no stale BAD read). */
            gnwmanager_set_status(GNWMANAGER_STATUS_HASH);
            state = (source_context->action == GNWMANAGER_ACTION_WRITE_FILE_TO_SD)
                  ? GNWMANAGER_DECOMPRESSING_SD
                  : GNWMANAGER_DECOMPRESSING;
            comm.retry_ack = comm.retry_request;
        }
        break;
    case GNWMANAGER_ERROR:
        /* Allow a new host command after release_context() cleared ready bits. */
        if (comm.contexts[0].ready || comm.contexts[1].ready) {
            state = GNWMANAGER_IDLE;
        }
        break;
    }
}


void gnwmanager_main(gnwmanager_status_t status)
{
    uint8_t reset_was_pressed = ((buttons_get() & (B_POWER | B_B)) != 0);

    memset((void *)&comm, 0, sizeof(comm));
    comm.status = status;

    gui.status = &comm.status;
    gui.progress = &comm.progress;
    gui.upload_in_progress = &comm.upload_in_progress;
    gui.download_in_progress = &comm.download_in_progress;

    // Draw LCD silvery background once.
    gui_fill(GUI_BACKGROUND_COLOR);

    if((*gui.status & 0xFFFF0000) == 0xbad00000){
        // Error happened during system setup.
        gnwmanager_gui_draw();
        while(true){
            uint8_t reset_pressed = ((buttons_get() & (B_POWER | B_B)) != 0);
            if((!reset_was_pressed) && reset_pressed){
                NVIC_SystemReset();
            }
            reset_was_pressed = reset_pressed;
            wdog_refresh();
        }
    }
    else{
        comm.flash_size = OSPI_GetSize();
        comm.min_erase_size = OSPI_GetSmallestEraseSize();
    }


    while (true) {
        uint8_t reset_pressed = ((buttons_get() & (B_POWER | B_B)) != 0);
        if((!reset_was_pressed) && reset_pressed && gnwmanager_is_idle()){
            NVIC_SystemReset();
        }
        reset_was_pressed = reset_pressed;

        if(comm.status_override){
            gui.status = &comm.status_override;
        }
        else{
            gui.status = &comm.status;
        }
        gnwmanager_run();
    }
}
