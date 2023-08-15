#include "odroid_overlay.h"
#include "segments.h"
#include "flashapp.h"
#include "flashapp_gui.h"

#define ACTIVE 0x0000
#define INACTIVE RGB24_TO_RGB565(0x5A, 0x5A, 0x5A)

#define CLOCK_DIGIT_SPACE 22
#define CLOCK_ORIGIN_Y 21
#define CLOCK_HOUR_ORIGIN_X 120
#define CLOCK_MINUTE_ORIGIN_X 172

#define ERROR1_ORIGIN_X 60
#define ERROR1_ORIGIN_Y 74

#define ERROR2_ORIGIN_X 110
#define ERROR2_ORIGIN_Y 102

#define RUN_ORIGIN_Y 145
#define RUN_ORIGIN_X 2
#define RUN_SPACING 31

#define DRAW(_x, _y, _img, _cond) odroid_overlay_draw_logo(_x, _y, _img, _cond ? ACTIVE : INACTIVE)

void flashapp_gui_draw(flashapp_gui_t *gui){
    DRAW(10, 16, &img_idle, *gui->status == FLASHAPP_STATUS_IDLE);
    DRAW(54, 16, &img_prog, *gui->status == FLASHAPP_STATUS_PROG);
    DRAW(10, 37, &img_erase, *gui->status == FLASHAPP_STATUS_ERASE);

    DRAW(CLOCK_HOUR_ORIGIN_X, CLOCK_ORIGIN_Y, &img_clock_8, true);
    DRAW(CLOCK_HOUR_ORIGIN_X + CLOCK_DIGIT_SPACE, CLOCK_ORIGIN_Y, &img_clock_8, true);
    DRAW(CLOCK_HOUR_ORIGIN_X + CLOCK_DIGIT_SPACE + img_clock_8.width + 4, CLOCK_ORIGIN_Y + 5, &img_colon, true);
    DRAW(CLOCK_MINUTE_ORIGIN_X, CLOCK_ORIGIN_Y, &img_clock_8, true);
    DRAW(CLOCK_MINUTE_ORIGIN_X + CLOCK_DIGIT_SPACE, CLOCK_ORIGIN_Y, &img_clock_8, true);


    DRAW(234, 26, &img_sleep, true);
    DRAW(232, 37, &img_z_0, true);
    DRAW(227, 26, &img_z_1, true);
    DRAW(221, 12, &img_z_2, true);

    DRAW(ERROR1_ORIGIN_X, ERROR1_ORIGIN_Y, &img_error, (*gui->status & 0xFFFF0000) == 0xbad00000);
    DRAW(ERROR1_ORIGIN_X + 65, ERROR1_ORIGIN_Y, &img_hash, false);
    DRAW(ERROR1_ORIGIN_X + 65 + 54, ERROR1_ORIGIN_Y, &img_mismatch, false);

    DRAW(ERROR2_ORIGIN_X, ERROR2_ORIGIN_Y, &img_flash, false);
    DRAW(ERROR2_ORIGIN_X + 65, ERROR2_ORIGIN_Y, &img_ram, false);

    DRAW(RUN_ORIGIN_X + 0 * RUN_SPACING, RUN_ORIGIN_Y, &img_run_0, false);
    DRAW(RUN_ORIGIN_X + 1 * RUN_SPACING, RUN_ORIGIN_Y, &img_run_1, false);
    DRAW(RUN_ORIGIN_X + 2 * RUN_SPACING, RUN_ORIGIN_Y, &img_run_2, false);
    DRAW(RUN_ORIGIN_X + 3 * RUN_SPACING, RUN_ORIGIN_Y, &img_run_3, true);
    DRAW(RUN_ORIGIN_X + 4 * RUN_SPACING, RUN_ORIGIN_Y, &img_run_4, false);
    DRAW(RUN_ORIGIN_X + 5 * RUN_SPACING, RUN_ORIGIN_Y, &img_run_5, false);
    DRAW(RUN_ORIGIN_X + 6 * RUN_SPACING, RUN_ORIGIN_Y, &img_run_6, false);
    DRAW(RUN_ORIGIN_X + 7 * RUN_SPACING, RUN_ORIGIN_Y, &img_run_7, false);
    DRAW(RUN_ORIGIN_X + 8 * RUN_SPACING, RUN_ORIGIN_Y, &img_run_8, false);
    DRAW(RUN_ORIGIN_X + 9 * RUN_SPACING, RUN_ORIGIN_Y, &img_run_9, false);

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
        if(i < 13)
            odroid_overlay_draw_logo(5 + i * 12, 200, progress[i % 10], true);
        else
            odroid_overlay_draw_logo(5 + i * 12, 200, progress[i % 10], false);
    }
}
