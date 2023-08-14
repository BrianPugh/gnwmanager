#pragma once

#include "stdbool.h"
#include "stdint.h"
#include "lcd.h"
#include "segments.h"

#define STATUS_HEIGHT (33)
#define HEADER_HEIGHT (47)

#define IMAGE_BANNER_WIDTH (GW_LCD_WIDTH)
#define IMAGE_BANNER_HEIGHT (32)

typedef struct {
    uint16_t bg_c;
    uint16_t main_c;
    uint16_t sel_c;
    uint16_t dis_c;
} colors_t;

extern colors_t *curr_colors;

typedef struct {
    char name[64];
    char status[64];
    const void *img_logo;
    const void *img_header;
    bool initialized;
    bool is_empty;
    void *arg;
} tab_t;

uint16_t get_darken_pixel(uint16_t color, uint16_t darken);
uint16_t get_shined_pixel(uint16_t color, uint16_t shined);

int  odroid_overlay_draw_text(uint16_t x, uint16_t y, uint16_t width, const char *text, uint16_t color, uint16_t color_bg);
void odroid_overlay_draw_rect(int x, int y, int width, int height, int border, uint16_t color);
void odroid_overlay_draw_fill_rect(int x, int y, int width, int height, uint16_t color);
int odroid_overlay_draw_text_line(uint16_t x_pos, uint16_t y_pos, uint16_t width, const char *text, uint16_t color, uint16_t color_bg);

void gui_draw_header(tab_t *tab);
void gui_draw_status(tab_t *tab);
void odroid_overlay_draw_logo(uint16_t x_pos, uint16_t y_pos, const retro_logo_image *logo, uint16_t color);
