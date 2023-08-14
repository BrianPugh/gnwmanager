#include <assert.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "flash.h"
#include "lcd.h"
#include "main.h"
#include "lzma.h"
#include "sha256.h"
#include "rg_rtc.h"
#include "odroid_overlay.h"
#include "flashapp_gui.h"


#define PERFORM_HASH_CHECK 1

typedef enum {  // For the flashapp state machine
    FLASHAPP_INIT                   ,
    FLASHAPP_IDLE                   ,
    FLASHAPP_DECOMPRESSING          ,
    FLASHAPP_CHECK_HASH_RAM         ,
    FLASHAPP_ERASE                  ,
    FLASHAPP_PROGRAM_NEXT           ,
    FLASHAPP_PROGRAM                ,
    FLASHAPP_CHECK_HASH_FLASH       ,

    FLASHAPP_ERROR = 0xF000,
} flashapp_state_t;

typedef enum { // For signaling program status to computer
    FLASHAPP_BOOTING = 0,

    FLASHAPP_STATUS_BAD_HASH_RAM    = 0xbad00001,
    FLASHAPP_STATUS_BAD_HAS_FLASH   = 0xbad00002,
    FLASHAPP_STATUS_NOT_ALIGNED     = 0xbad00003,

    FLASHAPP_STATUS_IDLE            = 0xcafe0000,
    FLASHAPP_STATUS_BUSY            = 0xcafe0001,
} flashapp_status_t;


typedef struct {
    union{
        struct{
            // This work context is ready for the on-device flashapp to process.
            uint32_t ready;

            // Number of bytes to program in the flash
            uint32_t size;

            // Where to program in the flash
            // offset into flash, not an absolute address 0x9XXX_XXXX
            uint32_t address;

            // Whether or not an erase should be performed
            uint32_t erase;

            // Number of bytes to be erased from program_address
            int32_t erase_bytes;

            // Set to 0 for no-compression
            uint32_t compressed_size;

            // The expected sha256 of the loaded binary
            uint8_t expected_sha256[32];

            volatile unsigned char *buffer;
        };
        struct{
            // Force spacing, allowing for backward-compatible additional variables
            char padding[4096];
        };
    };
} volatile work_context_t;

struct flashapp_comm {  // Values are read or written by the debugger
                        // only add attributes at the end (before work_buffers)
                        // so that addresses don't change.
    union {
        volatile struct{
            // Status register
            uint32_t program_status;

            // Host-setable timestamp; if 0, RTC is not updated.
            uint32_t utc_timestamp;

            // Current chunk index
            uint32_t program_chunk_idx;

            // Number of chunks
            uint32_t program_chunk_count;

            uint32_t active_context_index;

            /* You may add additional variables here and addresses will remain backwards compatible*/
        };
        struct {
            // Force spacing, allowing for backward-compatible additional variables
            char padding[4096];
        };
    };

    volatile work_context_t contexts[2];

    work_context_t active_context;

    volatile unsigned char buffer[2][256 << 10];

    unsigned char decompress_buffer[256 << 10];
};

static struct flashapp_comm comm_data __attribute__((section (".flashapp_comm")));
static struct flashapp_comm *comm = &comm_data;

static void flashapp_run(void)
{
    static flashapp_state_t state = FLASHAPP_INIT;
    static uint32_t context_counter = 1;
    static uint32_t erase_address = 0;  // Holds intermediate erase address.
                                        // Is it's own variable since context->address is used by both
                                        // programming and erasing.
    static uint32_t erase_bytes_left = 0;
    static uint32_t program_offset = 0; // Current offset into extflash that needs to be programmed
    static uint32_t program_bytes_remaining = 0;

    work_context_t *context = &comm->active_context;
    uint8_t program_calculated_sha256[32];

    wdog_refresh();

    switch (state) {
    case FLASHAPP_INIT:
        comm->program_chunk_count = 1;
        state++;
        break;
    case FLASHAPP_IDLE:
        OSPI_EnableMemoryMappedMode();

        if(comm->utc_timestamp){
            // Set time
            GW_SetUnixTime(comm->utc_timestamp);
            comm->utc_timestamp = 0;
        }

        // Attempt to find the next ready context in queue
        for(uint8_t i=0; i < 2; i++){
            if(comm->contexts[i].ready == context_counter){
                context_counter++;
                comm->active_context_index = i;
                memcpy((void *)context, (void *)&comm->contexts[i], sizeof(work_context_t));
                context->buffer = comm->buffer[i];

                if(context->erase){
                    erase_address = context->address;
                    erase_bytes_left = context->erase_bytes;

                    uint32_t smallest_erase = OSPI_GetSmallestEraseSize();

                    if (erase_address & (smallest_erase - 1)) {
                        // Address not aligned to smallest erase size
                        comm->program_status = FLASHAPP_STATUS_NOT_ALIGNED;
                        state = FLASHAPP_ERROR;
                        break;
                    }

                    // Round size up to nearest erase size if needed ?
                    if ((erase_bytes_left & (smallest_erase - 1)) != 0) {
                        erase_bytes_left += smallest_erase - (erase_bytes_left & (smallest_erase - 1));
                    }

                    // Start a non-blocking flash erase to run in the background
                    OSPI_DisableMemoryMappedMode();
                    OSPI_Erase(&erase_address, &erase_bytes_left, false);
                }
                comm->program_status = FLASHAPP_STATUS_BUSY;
                state++;
                break;
            }
        }
        comm->program_status = FLASHAPP_STATUS_IDLE;
        break;
    case FLASHAPP_DECOMPRESSING:
        if(context->compressed_size){
            // Decompress the data; nothing after this state should reference decompression.
            uint32_t n_decomp_bytes;
            n_decomp_bytes = lzma_inflate(comm->decompress_buffer, sizeof(comm->decompress_buffer),
                                          (uint8_t *)context->buffer, context->compressed_size);
            assert(n_decomp_bytes == context->size);
            context->buffer = comm->decompress_buffer;
            // We can now early release the context
            memset((void *)&comm->contexts[comm->active_context_index], 0, sizeof(work_context_t));
        }
        else{
            //The data came in NOT compressed
            memcpy((void *)comm->decompress_buffer, (void *)context->buffer, 256 << 10);
            context->buffer = comm->decompress_buffer;

            // We can now early release the context
            memset((void *)&comm->contexts[comm->active_context_index], 0, sizeof(work_context_t));
        }
        state++;
        break;
    case FLASHAPP_CHECK_HASH_RAM:
        // Calculate sha256 hash of the RAM first
#if PERFORM_HASH_CHECK
        sha256(program_calculated_sha256, (const BYTE*) context->buffer, context->size);

        if (memcmp((const void *)program_calculated_sha256, (const void *)context->expected_sha256, 32) != 0) {
            // Hashes don't match even in RAM, openocd loading failed.
            comm->program_status = FLASHAPP_STATUS_BAD_HASH_RAM;
            state = FLASHAPP_ERROR;
            break;
        }
#endif
        state++;
        break;
    case FLASHAPP_ERASE:
        if (!context->erase) {
            state = FLASHAPP_PROGRAM_NEXT;
            break;
        }

        OSPI_DisableMemoryMappedMode();
        if (context->erase_bytes == 0) {
            OSPI_NOR_WriteEnable();
            OSPI_ChipErase();
            state++;
        } else {
            // Returns true when all erasing has been complete.
            if (OSPI_Erase(&erase_address, &erase_bytes_left, true)) {
                state++;
            }
        }
        break;
    case FLASHAPP_PROGRAM_NEXT:
        program_offset = context->address;
        program_bytes_remaining = context->size;
        state++;
        break;
    case FLASHAPP_PROGRAM:
        OSPI_DisableMemoryMappedMode();
        if (program_bytes_remaining > 0) {
            uint32_t dest_page = program_offset / 256;
            uint32_t bytes_to_write = program_bytes_remaining > 256 ? 256 : program_bytes_remaining;
            OSPI_NOR_WriteEnable();
            OSPI_PageProgram(dest_page * 256, context->buffer, bytes_to_write);
            program_offset += bytes_to_write;
            context->buffer += bytes_to_write;
            program_bytes_remaining -= bytes_to_write;
        } else {
            state++;
        }
        break;
    case FLASHAPP_CHECK_HASH_FLASH:
        OSPI_EnableMemoryMappedMode();
#if PERFORM_HASH_CHECK
        // Calculate sha256 hash of the FLASH.
        sha256(program_calculated_sha256, (const BYTE*) (0x90000000 + context->address), context->size);

        if (memcmp((char *)program_calculated_sha256, (char *)context->expected_sha256, 32) != 0) {
            // Hashes don't match in FLASH, programming failed.
            comm->program_status = FLASHAPP_STATUS_BAD_HAS_FLASH;
            state = FLASHAPP_ERROR;
            break;
        }
#endif
        // Hash OK in FLASH
        state = FLASHAPP_IDLE;
        break;
    case FLASHAPP_ERROR:
        // Stay in state until reset.
        break;
    }
}

#define FS_MAGIC = "littlefs"
void find_littlefs(){
    uint32_t erase_size = OSPI_GetSmallestEraseSize();
    uint32_t flash_size = OSPI_GetSize();
    assert(0);  // Not implemented yet
}

#define FLASHAPP_BACKGROUND_COLOR RGB24_TO_RGB565(0x72, 0x73, 0x51)

void flashapp_main(void)
{
    memset((void *)comm, 0, sizeof(struct flashapp_comm));

    // Draw LCD silvery background once.
    odroid_overlay_draw_fill_rect(0, 0, 320, 240, FLASHAPP_BACKGROUND_COLOR);

    while (true) {
        // Run multiple times to skip rendering when programming
        for (int i = 0; i < 16; i++) {
            flashapp_run();
        }

        lcd_wait_for_vblank();
        flashapp_gui_draw();
    }
}
