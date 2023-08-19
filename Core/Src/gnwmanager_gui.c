#include "odroid_overlay.h"
#include "segments.h"
#include "gnwmanager.h"
#include "gnwmanager_gui.h"
#include <stdint.h>
#include <stdbool.h>
#include "rg_rtc.h"
#include "main.h"
#include "lcd.h"


void gui_fill(pixel_t color){
    pixel_t *dst = framebuffer;
    for (int x = 0; x < GW_LCD_WIDTH; x++) {
        for (int y = 0; y < GW_LCD_HEIGHT; y++) {
            dst[y * GW_LCD_WIDTH + x] = color;
        }
    }
}

void gui_draw_glyph(uint16_t x_pos, uint16_t y_pos, const retro_logo_image *logo, pixel_t color)
{
    pixel_t *dst_img = framebuffer;
    int w = (logo->width + 7) / 8;
    for (int i = 0; i < w; i++)
        for (int y = 0; y < logo->height; y++)
        {
            const char glyph = logo->logo[y * w + i];
            //for (int x = 0; x < 8; x++)
            if (glyph & 0x80)
                dst_img[(y + y_pos) * 320 + i * 8 + 0 + x_pos] = color;
            if (glyph & 0x40)
                dst_img[(y + y_pos) * 320 + i * 8 + 1 + x_pos] = color;
            if (glyph & 0x20)
                dst_img[(y + y_pos) * 320 + i * 8 + 2 + x_pos] = color;
            if (glyph & 0x10)
                dst_img[(y + y_pos) * 320 + i * 8 + 3 + x_pos] = color;
            if (glyph & 0x08)
                dst_img[(y + y_pos) * 320 + i * 8 + 4 + x_pos] = color;
            if (glyph & 0x04)
                dst_img[(y + y_pos) * 320 + i * 8 + 5 + x_pos] = color;
            if (glyph & 0x02)
                dst_img[(y + y_pos) * 320 + i * 8 + 6 + x_pos] = color;
            if (glyph & 0x01)
                dst_img[(y + y_pos) * 320 + i * 8 + 7 + x_pos] = color;
        }
};


#define CLOCK_DIGIT_SPACE 22
#define CLOCK_ORIGIN_Y 24
#define CLOCK_HOUR_ORIGIN_X 114
#define CLOCK_MINUTE_ORIGIN_X 166

#define ERROR1_ORIGIN_X 60
#define ERROR1_ORIGIN_Y 74

#define ERROR2_ORIGIN_X 110
#define ERROR2_ORIGIN_Y 102

#define RUN_ORIGIN_Y 145
#define RUN_ORIGIN_X 2
#define RUN_SPACING 31

#define DRAW(_x, _y, _img, _cond) gui_draw_glyph(_x, _y, _img, _cond ? GUI_SEGMENT_ACTIVE_COLOR : GUI_SEGMENT_INACTIVE_COLOR)

#define IS_ERROR_STATUS ((*gui.status & 0xFFFF0000) == 0xbad00000)
#define SLEEPING_THRESH 5
#define IS_SLEEPING (gui.counter_to_sleep == SLEEPING_THRESH)
#define IS_RUNNING (!IS_SLEEPING && !IS_ERROR_STATUS)

gnwmanager_gui_t gui;


static void draw_clock_digit(uint8_t val, uint16_t x, uint16_t y){
    const retro_logo_image *CLOCK_DIGITS[] = {
        &img_clock_0, &img_clock_1, &img_clock_2, &img_clock_3, &img_clock_4,
        &img_clock_5, &img_clock_6, &img_clock_7, &img_clock_8, &img_clock_9
    };
    DRAW(x, y, &img_clock_8, false);  // Draw shadow first
    DRAW(x, y, CLOCK_DIGITS[val], true);  // Draw active segments.
}

static void draw_clock(){
    HAL_RTC_GetTime(&hrtc, &GW_currentTime, RTC_FORMAT_BIN);
    HAL_RTC_GetDate(&hrtc, &GW_currentDate, RTC_FORMAT_BIN);

    // Draw colon
    DRAW(CLOCK_HOUR_ORIGIN_X + CLOCK_DIGIT_SPACE + img_clock_8.width + 4, CLOCK_ORIGIN_Y + 5, &img_colon, true);

    // segments
    uint8_t hours_tens_val = GW_currentTime.Hours / 10;
    if(hours_tens_val){
        draw_clock_digit(hours_tens_val, CLOCK_HOUR_ORIGIN_X, CLOCK_ORIGIN_Y);
    }
    else{
        DRAW(CLOCK_HOUR_ORIGIN_X, CLOCK_ORIGIN_Y, &img_clock_8, false);
    }

    draw_clock_digit(GW_currentTime.Hours % 10,   CLOCK_HOUR_ORIGIN_X + CLOCK_DIGIT_SPACE, CLOCK_ORIGIN_Y);
    draw_clock_digit(GW_currentTime.Minutes / 10, CLOCK_MINUTE_ORIGIN_X, CLOCK_ORIGIN_Y);
    draw_clock_digit(GW_currentTime.Minutes % 10, CLOCK_MINUTE_ORIGIN_X + CLOCK_DIGIT_SPACE, CLOCK_ORIGIN_Y);
}

void gnwmanager_gui_draw(bool step){
    if(*gui.status != GNWMANAGER_STATUS_IDLE){
        gui.counter_to_sleep = 0;
    }

    if(step){
        if(!IS_SLEEPING && *gui.status == GNWMANAGER_STATUS_IDLE)
            gui.counter_to_sleep++;

        gui.sleep_z_state = IS_SLEEPING ? (gui.sleep_z_state + 1) % 4 : 0;
        gui.run_state = IS_RUNNING ? (gui.run_state + 1) % 10 : 0;
    }

    DRAW(10, 16, &img_idle, *gui.status == GNWMANAGER_STATUS_IDLE);
    DRAW(54, 16, &img_prog, *gui.status == GNWMANAGER_STATUS_PROG);
    DRAW(10, 37, &img_erase, *gui.status == GNWMANAGER_STATUS_ERASE);

    draw_clock();

    DRAW(234, 26, &img_sleep, IS_SLEEPING);
    DRAW(232, 37, &img_z_0, IS_SLEEPING && gui.sleep_z_state > 0);
    DRAW(227, 26, &img_z_1, IS_SLEEPING && gui.sleep_z_state > 1);
    DRAW(221, 12, &img_z_2, IS_SLEEPING && gui.sleep_z_state > 2);

    DRAW(ERROR1_ORIGIN_X, ERROR1_ORIGIN_Y, &img_error, IS_ERROR_STATUS);
    DRAW(ERROR1_ORIGIN_X + 65, ERROR1_ORIGIN_Y, &img_hash,
            (*gui.status == GNWMANAGER_STATUS_HASH)
            || *gui.status == GNWMANAGER_STATUS_BAD_HASH_FLASH
            || *gui.status == GNWMANAGER_STATUS_BAD_HASH_RAM
    );
    DRAW(ERROR1_ORIGIN_X + 65 + 54, ERROR1_ORIGIN_Y, &img_mismatch,
            *gui.status == GNWMANAGER_STATUS_BAD_HASH_FLASH
            || *gui.status == GNWMANAGER_STATUS_BAD_HASH_RAM
    );

    DRAW(ERROR2_ORIGIN_X, ERROR2_ORIGIN_Y, &img_flash,
            *gui.status == GNWMANAGER_STATUS_BAD_HASH_FLASH
    );
    DRAW(ERROR2_ORIGIN_X + 65, ERROR2_ORIGIN_Y, &img_ram,
            *gui.status == GNWMANAGER_STATUS_BAD_HASH_RAM
    );

    const retro_logo_image* run[] = {
        &img_run_0,
        &img_run_1,
        &img_run_2,
        &img_run_3,
        &img_run_4,
        &img_run_5,
        &img_run_6,
        &img_run_7,
        &img_run_8,
        &img_run_9,
    };
    for(uint8_t i=0; i<10; i++){
        DRAW(RUN_ORIGIN_X + i * RUN_SPACING, RUN_ORIGIN_Y, run[i],
                (i == gui.run_state) && IS_RUNNING);
    }

    const retro_logo_image* progress[] = {
        &img_progress_0,
        &img_progress_1,
        &img_progress_2,
        &img_progress_3,
        &img_progress_4,
        &img_progress_5,
        &img_progress_6,
        &img_progress_7,
        &img_progress_8,
        &img_progress_9,
    };

    for(uint8_t i=0; i < 26; i++){
        DRAW(5 + i * 12, 200, progress[i % 10], i <= *gui.progress);
    }
}
