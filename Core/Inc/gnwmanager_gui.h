#pragma once

#include "gnwmanager.h"
#include <float.h>
#include "lcd.h"

#define RED_COMPONENT(c)     (((c) & 0xF800) >> 11)
#define GREEN_COMPONENT(c)   (((c) & 0x07E0) >> 5)
#define BLUE_COMPONENT(c)    ((c) & 0x001F)

#define RGB24_TO_RGB565(r, g, b) ((pixel_t)( ((r) >> 3) << 11 ) | ( ((g) >> 2) << 5 ) | ( (b) >> 3 ))
#define DARKEN(c, multiplier)  (pixel_t)((((pixel_t)(RED_COMPONENT(c) * multiplier) & 0x1F) << 11) | \
                                     (((pixel_t)(GREEN_COMPONENT(c) * multiplier) & 0x3F) << 5) | \
                                     ((pixel_t)(BLUE_COMPONENT(c) * multiplier) & 0x1F))

#define GUI_BACKGROUND_COLOR RGB24_TO_RGB565(0xC6, 0xCA, 0xAF)
#define GUI_SEGMENT_INACTIVE_COLOR DARKEN(GUI_BACKGROUND_COLOR, 0.8)
#define GUI_SEGMENT_ACTIVE_COLOR 0x0000

typedef struct{
    volatile gnwmanager_status_t *status;
    volatile uint32_t *progress;

    uint8_t sleep_z_state;  // [0, 3]
    uint8_t counter_to_sleep;

    uint8_t run_state;  // [0, 9]
} gnwmanager_gui_t;

extern gnwmanager_gui_t gui;

void gui_fill(pixel_t color);
void gui_draw_glyph(uint16_t x_pos, uint16_t y_pos, const retro_logo_image *logo, uint16_t color);

void gnwmanager_gui_draw(bool step);
