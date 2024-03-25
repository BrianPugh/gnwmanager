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
#include "rg_rtc.h"
#include "gnwmanager.h"
#include "gnwmanager_gui.h"
#include "buttons.h"


typedef enum {  // For the gnwmanager state machine
    GNWMANAGER_IDLE                   ,
    GNWMANAGER_DECOMPRESSING          ,
    GNWMANAGER_CHECK_HASH_RAM         ,
    GNWMANAGER_ERASE                  ,
    GNWMANAGER_ERASE_FINISH           ,
    GNWMANAGER_PROGRAM                ,
    GNWMANAGER_CHECK_HASH_FLASH       ,

    GNWMANAGER_ERROR = 0xF000,
} gnwmanager_state_t;


enum gnwmanager_action {
    GNWMANAGER_ACTION_ERASE_AND_FLASH = 0,
    GNWMANAGER_ACTION_HASH = 1,
};


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

            volatile uint32_t upload_in_progress;  // computer -> device

            volatile uint32_t download_in_progress;  // device -> computer

            volatile uint8_t expected_hash[32];

            volatile uint8_t actual_hash[32];
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
            gnwmanager_set_status(GNWMANAGER_STATUS_IDLE);
            break;
        }
        context_counter++;

        switch(source_context->action){
            case GNWMANAGER_ACTION_ERASE_AND_FLASH:
                // The rest of this function
                break;
            case GNWMANAGER_ACTION_HASH:
                gnwmanager_set_status(GNWMANAGER_STATUS_HASH);
                gnwmanager_action_hash(source_context);
                return;
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
        state++;
        break;
    case GNWMANAGER_DECOMPRESSING:
        if(working_context->compressed_size){
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
            memcpy(comm.actual_hash, program_calculated_sha256, 32);
            memcpy(comm.expected_hash, working_context->expected_sha256, 32);
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
            memcpy(comm.actual_hash, program_calculated_sha256, 32);
            memcpy(comm.expected_hash, working_context->expected_sha256, 32);
            gnwmanager_set_status(GNWMANAGER_STATUS_BAD_HASH_FLASH);
            state = GNWMANAGER_ERROR;
            break;
        }
        // Hash OK in FLASH
        state = GNWMANAGER_IDLE;
        break;
    case GNWMANAGER_ERROR:
        // Stay in state until reset.
        break;
    }
}


void gnwmanager_main(gnwmanager_status_t status)
{
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
            if(buttons_get() & B_POWER){
                NVIC_SystemReset();
            }
            wdog_refresh();
        }
    }
    else{
        comm.flash_size = OSPI_GetSize();
        comm.min_erase_size = OSPI_GetSmallestEraseSize();
    }


    while (true) {
        if(buttons_get() & B_POWER){
            NVIC_SystemReset();
        }

        if(comm.status_override){
            gui.status = &comm.status_override;
        }
        else{
            gui.status = &comm.status;
        }
        gnwmanager_run();
    }
}
