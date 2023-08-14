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
#include "odroid_overlay.h"
#include "rg_rtc.h"
#include "flashapp_gui.h"


#define DBG(...) printf(__VA_ARGS__)
// #define DBG(...)


static const int font_height = 8;
static const int font_width = 8;

#define LIST_X_OFFSET    (0)
#define LIST_Y_OFFSET    (STATUS_HEIGHT)
#define LIST_WIDTH       (GW_LCD_WIDTH)
#define LIST_HEIGHT      (GW_LCD_HEIGHT - STATUS_HEIGHT - HEADER_HEIGHT)
#define LIST_LINE_HEIGHT (font_height + 2)
#define LIST_LINE_COUNT  (LIST_HEIGHT / LIST_LINE_HEIGHT)

#define PROGRESS_X_OFFSET (GW_LCD_WIDTH / 5 / 2)
#define PROGRESS_Y_OFFSET (LIST_Y_OFFSET + 9 * LIST_LINE_HEIGHT)
#define PROGRESS_WIDTH    (4 * (PROGRESS_X_OFFSET * 2))
#define PROGRESS_HEIGHT   (2 * LIST_LINE_HEIGHT)

#define PERFORM_HASH_CHECK 1

typedef enum {
    FLASHAPP_INIT                   ,
    FLASHAPP_IDLE                   ,
    FLASHAPP_START                  ,
    FLASHAPP_DECOMPRESSING          ,
    FLASHAPP_CHECK_HASH_RAM_NEXT    ,
    FLASHAPP_CHECK_HASH_RAM         ,
    FLASHAPP_ERASE_NEXT             ,
    FLASHAPP_ERASE                  ,
    FLASHAPP_PROGRAM_NEXT           ,
    FLASHAPP_PROGRAM                ,
    FLASHAPP_CHECK_HASH_FLASH_NEXT  ,
    FLASHAPP_CHECK_HASH_FLASH       ,

    FLASHAPP_FINAL                  = 0x0C,
    FLASHAPP_ERROR                  = 0x0D,
} flashapp_state_t;

typedef enum {
    FLASHAPP_BOOTING = 0,

    FLASHAPP_STATUS_BAD_HASH_RAM    = 0xbad00001,
    FLASHAPP_STATUS_BAD_HAS_FLASH   = 0xbad00002,
    FLASHAPP_STATUS_NOT_ALIGNED     = 0xbad00003,

    FLASHAPP_STATUS_IDLE            = 0xcafe0000,
    FLASHAPP_STATUS_DONE            = 0xcafe0001,
    FLASHAPP_STATUS_BUSY            = 0xcafe0002,
} flashapp_status_t;

/* flashapp_t is only modified by program, not host computer */
typedef struct {
    tab_t    tab;
    uint32_t erase_address;
    uint32_t erase_bytes_left;
    uint32_t current_program_address;
    uint32_t program_bytes_left;
    uint8_t* program_buf;
    uint32_t progress_max;
    uint32_t progress_value;
    uint32_t context_counter;
} flashapp_t;

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
            // FlashApp state-machine state
            uint32_t flashapp_state;

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

// framebuffer1 is used as an actual framebuffer.
// framebuffer2 and onwards is used as a buffer for the flash.
static struct flashapp_comm comm_data __attribute__((section (".flashapp_comm")));
static struct flashapp_comm *comm = &comm_data;

#if 0
static void draw_text_line_centered(uint16_t y_pos,
                                    const char *text,
                                    uint16_t color,
                                    uint16_t color_bg)
{
    int width = strlen(text) * font_width;
    int x_pos = GW_LCD_WIDTH / 2 - width / 2;

    odroid_overlay_draw_text_line(x_pos, y_pos, width, text, color, color_bg);
}

static void draw_progress(flashapp_t *flashapp)
{
    char progress_str[16];

    odroid_overlay_draw_fill_rect(0, LIST_Y_OFFSET, LIST_WIDTH, LIST_HEIGHT, curr_colors->bg_c);

    draw_text_line_centered(LIST_Y_OFFSET + LIST_LINE_HEIGHT, flashapp->tab.status, curr_colors->sel_c, curr_colors->bg_c);

    draw_text_line_centered(LIST_Y_OFFSET + 5 * LIST_LINE_HEIGHT, flashapp->tab.name, curr_colors->sel_c, curr_colors->bg_c);

    if (flashapp->progress_max != 0) {
        int32_t progress_percent = (100 * (uint64_t)flashapp->progress_value) / flashapp->progress_max;
        int32_t progress_width = (PROGRESS_WIDTH * (uint64_t)flashapp->progress_value) / flashapp->progress_max;

        sprintf(progress_str, "%ld%%", progress_percent);

        odroid_overlay_draw_fill_rect(PROGRESS_X_OFFSET,
                                      PROGRESS_Y_OFFSET,
                                      PROGRESS_WIDTH,
                                      PROGRESS_HEIGHT,
                                      curr_colors->main_c);

        odroid_overlay_draw_fill_rect(PROGRESS_X_OFFSET,
                                      PROGRESS_Y_OFFSET,
                                      progress_width,
                                      PROGRESS_HEIGHT,
                                      curr_colors->sel_c);

        draw_text_line_centered(LIST_Y_OFFSET + 8 * LIST_LINE_HEIGHT, progress_str, curr_colors->sel_c, curr_colors->bg_c);
    }
}

static void redraw(flashapp_t *flashapp)
{
    //gui_draw_header(&flashapp->tab); // really a footer, but whatever
    //gui_draw_status(&flashapp->tab);

    //draw_progress(flashapp);
}
#endif


static void state_set(flashapp_state_t state_next)
{
    printf("State: %ld -> %d\n", comm->flashapp_state, state_next);

    comm->flashapp_state = state_next;
}

static void state_inc(void)
{
    state_set(comm->flashapp_state + 1);
}

static void flashapp_run(flashapp_t *flashapp)
{
    work_context_t *context = &comm->active_context;
    uint8_t program_calculated_sha256[32];

    switch (comm->flashapp_state) {
    case FLASHAPP_INIT:
        comm->program_chunk_count = 1;
        flashapp->progress_value = 0;
        flashapp->progress_max = 0;

        state_inc();
        break;
    case FLASHAPP_IDLE:
        OSPI_EnableMemoryMappedMode();

        // Notify that we are ready to start
        comm->program_status = FLASHAPP_STATUS_IDLE;
        flashapp->progress_value = 0;
        flashapp->progress_max = 0;

        if(comm->utc_timestamp){
            // Set time
            GW_SetUnixTime(comm->utc_timestamp);
            comm->utc_timestamp = 0;
        }

        // Attempt to find the next ready context in queue
        for(uint8_t i=0; i < 2; i++){
            if(comm->contexts[i].ready == flashapp->context_counter){
                flashapp->context_counter++;
                comm->active_context_index = i;
                memcpy((void *)context, (void *)&comm->contexts[i], sizeof(work_context_t));
                context->buffer = comm->buffer[i];

                if(context->erase){
                    flashapp->erase_address = context->address;
                    flashapp->erase_bytes_left = context->erase_bytes;

                    uint32_t smallest_erase = OSPI_GetSmallestEraseSize();

                    if (flashapp->erase_address & (smallest_erase - 1)) {
                        sprintf(flashapp->tab.name, "** Address not aligned to smallest erase size! **");
                        comm->program_status = FLASHAPP_STATUS_NOT_ALIGNED;
                        state_set(FLASHAPP_ERROR);
                        break;
                    }

                    // Round size up to nearest erase size if needed ?
                    if ((flashapp->erase_bytes_left & (smallest_erase - 1)) != 0) {
                        flashapp->erase_bytes_left += smallest_erase - (flashapp->erase_bytes_left & (smallest_erase - 1));
                    }

                    // Start a non-blocking flash erase to run in the background
                    OSPI_DisableMemoryMappedMode();
                    OSPI_Erase(&flashapp->erase_address, &flashapp->erase_bytes_left, false);
                }
                state_inc();
                break;
            }
        }
        if(comm->flashapp_state == FLASHAPP_IDLE)
            sprintf(flashapp->tab.name, "Waiting for command...");

        break;
    case FLASHAPP_START:
        sprintf(flashapp->tab.name, "Processing...");
        comm->program_status = FLASHAPP_STATUS_BUSY;
        state_inc();
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
        state_inc();
        break;
    case FLASHAPP_CHECK_HASH_RAM_NEXT:
        sprintf(flashapp->tab.name, "Checking hash in RAM (%ld bytes)", context->size);
        state_inc();
        break;
    case FLASHAPP_CHECK_HASH_RAM:
        // Calculate sha256 hash of the RAM first
#if PERFORM_HASH_CHECK
        sha256(program_calculated_sha256, (const BYTE*) context->buffer, context->size);

        if (memcmp((const void *)program_calculated_sha256, (const void *)context->expected_sha256, 32) != 0) {
            // Hashes don't match even in RAM, openocd loading failed.
            sprintf(flashapp->tab.name, "*** Hash mismatch in RAM ***");
            comm->program_status = FLASHAPP_STATUS_BAD_HASH_RAM;
            state_set(FLASHAPP_ERROR);
            break;
        } else {
            sprintf(flashapp->tab.name, "Hash OK in RAM");
        }
#endif
        state_inc();
        break;
    case FLASHAPP_ERASE_NEXT:
        if (context->erase) {
            if (context->erase_bytes == 0) {
                sprintf(flashapp->tab.name, "Performing Chip Erase (takes time)");
            }
            else {
                sprintf(flashapp->tab.name, "Erasing %ld bytes...", flashapp->erase_bytes_left);
                printf("Erasing %ld bytes at 0x%08lx\n", context->erase_bytes, flashapp->erase_address);
            }
            state_inc();
        } else {
            state_set(FLASHAPP_PROGRAM_NEXT);
        }
        break;
    case FLASHAPP_ERASE:
        OSPI_DisableMemoryMappedMode();
        if (context->erase_bytes == 0) {
            OSPI_NOR_WriteEnable();
            OSPI_ChipErase();
            state_inc();
        } else {
            if (OSPI_Erase(&flashapp->erase_address, &flashapp->erase_bytes_left, true)) {
                state_inc();
            }
        }
        break;
    case FLASHAPP_PROGRAM_NEXT:
        sprintf(flashapp->tab.name, "Programming...");
        flashapp->progress_value = 0;
        flashapp->current_program_address = context->address;

        flashapp->progress_max = context->size;
        flashapp->program_bytes_left = context->size;
        flashapp->program_buf = (unsigned char*)context->buffer;

        state_inc();
        break;
    case FLASHAPP_PROGRAM:
        OSPI_DisableMemoryMappedMode();
        if (flashapp->program_bytes_left > 0) {
            uint32_t dest_page = flashapp->current_program_address / 256;
            uint32_t bytes_to_write = flashapp->program_bytes_left > 256 ? 256 : flashapp->program_bytes_left;
            OSPI_NOR_WriteEnable();
            OSPI_PageProgram(dest_page * 256, flashapp->program_buf, bytes_to_write);
            flashapp->current_program_address += bytes_to_write;
            flashapp->program_buf += bytes_to_write;
            flashapp->program_bytes_left -= bytes_to_write;
            flashapp->progress_value = flashapp->progress_max - flashapp->program_bytes_left;
        } else {
            state_inc();
        }
        break;
    case FLASHAPP_CHECK_HASH_FLASH_NEXT:
        sprintf(flashapp->tab.name, "Checking hash in FLASH");
        OSPI_EnableMemoryMappedMode();
        state_inc();
        break;
    case FLASHAPP_CHECK_HASH_FLASH:
#if PERFORM_HASH_CHECK
        // Calculate sha256 hash of the FLASH.
        sha256(program_calculated_sha256, (const BYTE*) (0x90000000 + context->address), context->size);

        if (memcmp((char *)program_calculated_sha256, (char *)context->expected_sha256, 32) != 0) {
            // Hashes don't match in FLASH, programming failed.
            sprintf(flashapp->tab.name, "*** Hash mismatch in FLASH ***");
            comm->program_status = FLASHAPP_STATUS_BAD_HAS_FLASH;
            state_set(FLASHAPP_ERROR);
            break;
        }
#endif
        sprintf(flashapp->tab.name, "Hash OK in FLASH.");
        state_set(FLASHAPP_IDLE);
        break;
    case FLASHAPP_FINAL:
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

#define FLASHAPP_BACKGROUND_COLOR _2C_(0x727351)

void flashapp_main(void)
{
    flashapp_t flashapp = {};
    flashapp.context_counter = 1;
#if 0
    flashapp.tab.img_header = &logo_flash;
    flashapp.tab.img_logo = &logo_gnw;
#endif

    memset((void *)comm, 0, sizeof(struct flashapp_comm));

    odroid_overlay_draw_fill_rect(0, 0, 320, 240, FLASHAPP_BACKGROUND_COLOR);

    while (true) {
        if (comm->program_chunk_count == 1) {
            sprintf(flashapp.tab.status, "G&W FlashApp: Awaiting Data");
        } else {
            sprintf(flashapp.tab.status, "G&W FlashApp: Received (%ld/%ld)",
                    comm->program_chunk_idx, comm->program_chunk_count);
        }

        // Run multiple times to skip rendering when programming
        for (int i = 0; i < 16; i++) {
            wdog_refresh();
            flashapp_run(&flashapp);
        }

        lcd_wait_for_vblank();
        flashapp_gui_draw();
    }
}
