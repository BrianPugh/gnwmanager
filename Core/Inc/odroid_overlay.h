#pragma once

#include "stdbool.h"
#include "stdint.h"
#include "lcd.h"
#include "segments.h"


int  odroid_overlay_draw_text(uint16_t x, uint16_t y, uint16_t width, const char *text, uint16_t color, uint16_t color_bg);
void odroid_overlay_draw_rect(int x, int y, int width, int height, int border, uint16_t color);
void odroid_overlay_draw_fill_rect(int x, int y, int width, int height, uint16_t color);
int odroid_overlay_draw_text_line(uint16_t x_pos, uint16_t y_pos, uint16_t width, const char *text, uint16_t color, uint16_t color_bg);
void odroid_overlay_draw_logo(uint16_t x_pos, uint16_t y_pos, const retro_logo_image *logo, uint16_t color);
