#include "odroid_overlay.h"
#include "segments.h"
#include "flashapp_gui.h"

#define ACTIVE 0x0000
#define INACTIVE RGB24_TO_RGB565(0x56, 0x56, 0x56)

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

void flashapp_gui_draw(){
    odroid_overlay_draw_logo(10, 16, &img_idle, ACTIVE);
    odroid_overlay_draw_logo(54, 16, &img_prog, INACTIVE);
    odroid_overlay_draw_logo(10, 37, &img_erase, INACTIVE);

    odroid_overlay_draw_logo(CLOCK_HOUR_ORIGIN_X, CLOCK_ORIGIN_Y, &img_clock_8, ACTIVE);
    odroid_overlay_draw_logo(CLOCK_HOUR_ORIGIN_X + CLOCK_DIGIT_SPACE, CLOCK_ORIGIN_Y, &img_clock_8, ACTIVE);
    odroid_overlay_draw_logo(CLOCK_HOUR_ORIGIN_X + CLOCK_DIGIT_SPACE + img_clock_8.width + 4, CLOCK_ORIGIN_Y + 5, &img_colon, ACTIVE);
    odroid_overlay_draw_logo(CLOCK_MINUTE_ORIGIN_X, CLOCK_ORIGIN_Y, &img_clock_8, ACTIVE);
    odroid_overlay_draw_logo(CLOCK_MINUTE_ORIGIN_X + CLOCK_DIGIT_SPACE, CLOCK_ORIGIN_Y, &img_clock_8, ACTIVE);


    odroid_overlay_draw_logo(234, 26, &img_sleep, ACTIVE);
    odroid_overlay_draw_logo(232, 37, &img_z_0, ACTIVE);
    odroid_overlay_draw_logo(227, 26, &img_z_1, ACTIVE);
    odroid_overlay_draw_logo(221, 12, &img_z_2, ACTIVE);

    odroid_overlay_draw_logo(ERROR1_ORIGIN_X, ERROR1_ORIGIN_Y, &img_error, INACTIVE);
    odroid_overlay_draw_logo(ERROR1_ORIGIN_X + 65, ERROR1_ORIGIN_Y, &img_hash, INACTIVE);
    odroid_overlay_draw_logo(ERROR1_ORIGIN_X + 65 + 54, ERROR1_ORIGIN_Y, &img_mismatch, INACTIVE);

    odroid_overlay_draw_logo(ERROR2_ORIGIN_X, ERROR2_ORIGIN_Y, &img_flash, INACTIVE);
    odroid_overlay_draw_logo(ERROR2_ORIGIN_X + 65, ERROR2_ORIGIN_Y, &img_ram, INACTIVE);

    odroid_overlay_draw_logo(RUN_ORIGIN_X + 0 * RUN_SPACING, RUN_ORIGIN_Y, &img_run_0, ACTIVE);
    odroid_overlay_draw_logo(RUN_ORIGIN_X + 1 * RUN_SPACING, RUN_ORIGIN_Y, &img_run_1, ACTIVE);
    odroid_overlay_draw_logo(RUN_ORIGIN_X + 2 * RUN_SPACING, RUN_ORIGIN_Y, &img_run_2, ACTIVE);
    odroid_overlay_draw_logo(RUN_ORIGIN_X + 3 * RUN_SPACING, RUN_ORIGIN_Y, &img_run_3, ACTIVE);
    odroid_overlay_draw_logo(RUN_ORIGIN_X + 4 * RUN_SPACING, RUN_ORIGIN_Y, &img_run_4, ACTIVE);
    odroid_overlay_draw_logo(RUN_ORIGIN_X + 5 * RUN_SPACING, RUN_ORIGIN_Y, &img_run_5, ACTIVE);
    odroid_overlay_draw_logo(RUN_ORIGIN_X + 6 * RUN_SPACING, RUN_ORIGIN_Y, &img_run_6, ACTIVE);
    odroid_overlay_draw_logo(RUN_ORIGIN_X + 7 * RUN_SPACING, RUN_ORIGIN_Y, &img_run_7, ACTIVE);
    odroid_overlay_draw_logo(RUN_ORIGIN_X + 8 * RUN_SPACING, RUN_ORIGIN_Y, &img_run_8, ACTIVE);
    odroid_overlay_draw_logo(RUN_ORIGIN_X + 9 * RUN_SPACING, RUN_ORIGIN_Y, &img_run_9, ACTIVE);

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
        odroid_overlay_draw_logo(5 + i * 12, 200, progress[i % 10], ACTIVE);
    }
}
