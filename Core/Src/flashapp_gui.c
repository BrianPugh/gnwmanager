#include "odroid_overlay.h"
#include "segments.h"
#include "flashapp.h"
#include "flashapp_gui.h"
#include <stdint.h>
#include <stdbool.h>
#include "rg_rtc.h"
#include "main.h"

#define ACTIVE 0x0000
#define INACTIVE RGB24_TO_RGB565(0x60, 0x60, 0x60)

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

#define DRAW(_x, _y, _img, _cond) odroid_overlay_draw_logo(_x, _y, _img, _cond ? ACTIVE : INACTIVE)

#define SLEEPING_THRESH 5
#define IS_SLEEPING (gui.counter_to_sleep == SLEEPING_THRESH)
#define IS_RUNNING (!IS_SLEEPING)

flashapp_gui_t gui;


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

void flashapp_gui_draw(bool step){
    if(*gui.status != FLASHAPP_STATUS_IDLE){
        gui.counter_to_sleep = 0;
    }

    if(step){
        if(!IS_SLEEPING && *gui.status == FLASHAPP_STATUS_IDLE)
            gui.counter_to_sleep++;

        gui.sleep_z_state = IS_SLEEPING ? (gui.sleep_z_state + 1) % 4 : 0;
        gui.run_state = IS_RUNNING ? (gui.run_state + 1) % 10 : 0;
    }

    DRAW(10, 16, &img_idle, *gui.status == FLASHAPP_STATUS_IDLE);
    DRAW(54, 16, &img_prog, *gui.status == FLASHAPP_STATUS_PROG);
    DRAW(10, 37, &img_erase, *gui.status == FLASHAPP_STATUS_ERASE);

    draw_clock();

    DRAW(234, 26, &img_sleep, IS_SLEEPING);
    DRAW(232, 37, &img_z_0, IS_SLEEPING && gui.sleep_z_state > 0);
    DRAW(227, 26, &img_z_1, IS_SLEEPING && gui.sleep_z_state > 1);
    DRAW(221, 12, &img_z_2, IS_SLEEPING && gui.sleep_z_state > 2);

    DRAW(ERROR1_ORIGIN_X, ERROR1_ORIGIN_Y, &img_error, (*gui.status & 0xFFFF0000) == 0xbad00000);
    DRAW(ERROR1_ORIGIN_X + 65, ERROR1_ORIGIN_Y, &img_hash, (*gui.status == FLASHAPP_STATUS_HASH));
    DRAW(ERROR1_ORIGIN_X + 65 + 54, ERROR1_ORIGIN_Y, &img_mismatch, false);

    DRAW(ERROR2_ORIGIN_X, ERROR2_ORIGIN_Y, &img_flash, false);
    DRAW(ERROR2_ORIGIN_X + 65, ERROR2_ORIGIN_Y, &img_ram, false);

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
