#include "odroid_overlay.h"
#include "font_basic.h"
#include <string.h>
#include <stdio.h>
#include "rg_rtc.h"
#include "main.h"
#include "flashapp_gui.h"

static pixel_t overlay_buffer[GW_LCD_WIDTH * 32 * 2] __attribute__((aligned(4)));


#define _2C_(C) (((C >> 8) & 0xF800) | ((C >> 5) & 0x7E0) | ((C >> 3) & 0x1F))

static const colors_t gui_colors[] = {
    //Main Theme color
    {_2C_(0x000000), _2C_(0x600000), _2C_(0xD08828), _2C_(0x584010)},
};
colors_t *curr_colors = (colors_t *)(&gui_colors[0]);


uint16_t get_darken_pixel(uint16_t color, uint16_t darken)
{
    int16_t r = (int16_t)((color & 0b1111100000000000) * darken / 100) & 0b1111100000000000;
    int16_t g = (int16_t)((color & 0b0000011111100000) * darken / 100) & 0b0000011111100000;
    int16_t b = (int16_t)((color & 0b0000000000011111) * darken / 100) & 0b0000000000011111;
    return r | g | b;
}

uint16_t get_shined_pixel(uint16_t color, uint16_t shined)
{
    int16_t r = (int16_t)((color & 0b1111100000000000) + (0b1111100000000000 - (color & 0b1111100000000000)) / 100 * shined) & 0b1111100000000000;
    int16_t g = (int16_t)((color & 0b0000011111100000) + (0b0000011111100000 - (color & 0b0000011111100000)) / 100 * shined) & 0b0000011111100000;
    int16_t b = (int16_t)((color & 0b0000000000011111) + (0b0000000000011111 - (color & 0b0000000000011111)) * shined / 100) & 0b0000000000011111;
    return r | g | b;
}

void odroid_display_write_rect(short left, short top, short width, short height, short stride, const uint16_t* buffer)
{
    pixel_t *dest = framebuffer;

    for (short y = 0; y < height; y++) {
        if ((y + top) >= GW_LCD_WIDTH)
            return;
        pixel_t *dest_row = &dest[(y + top) * GW_LCD_WIDTH + left];
        memcpy(dest_row, &buffer[y * stride], width * sizeof(pixel_t));
    }
}

// Same as odroid_display_write_rect but stride is assumed to be width (for backwards compat)
void odroid_display_write(short left, short top, short width, short height, const uint16_t* buffer)
{
    odroid_display_write_rect(left, top, width, height, width, buffer);
}

int odroid_overlay_draw_text_line(uint16_t x_pos, uint16_t y_pos, uint16_t width, const char *text, uint16_t color, uint16_t color_bg)
{
    int font_height = 8;
    int font_width = 8;
    int x_offset = 0;
    int text_len = strlen(text);

    for (int i = 0; i < (width / font_width); i++)
    {
        const char *glyph = font8x8_basic[(i < text_len) ? text[i] : ' '];
        for (int y = 0; y < font_height; y++)
        {
            int offset = x_offset + (width * y);
            for (int x = 0; x < 8; x++)
                overlay_buffer[offset + x] = (glyph[y] & (1 << x)) ? color : color_bg;
        }
        x_offset += font_width;
    }

    odroid_display_write(x_pos, y_pos, width, font_height, overlay_buffer);

    return font_height;
}

int odroid_overlay_draw_text(uint16_t x_pos, uint16_t y_pos, uint16_t width, const char *text, uint16_t color, uint16_t color_bg)
{
    int text_len = 1;
    int height = 0;

    if (text == NULL || text[0] == 0)
        text = " ";

    text_len = strlen(text);

    if (width < 1)
        width = text_len * 8;

    if (width > (GW_LCD_WIDTH - x_pos))
        width = (GW_LCD_WIDTH - x_pos);

    int line_len = width / 8;
    char buffer[GW_LCD_WIDTH / 8 + 1];

    for (int pos = 0; pos < text_len;)
    {
        sprintf(buffer, "%.*s", line_len, text + pos);
        if (strchr(buffer, '\n'))
            *(strchr(buffer, '\n')) = 0;
        height += odroid_overlay_draw_text_line(x_pos, y_pos + height, width, buffer, color, color_bg);
        pos += strlen(buffer);
        if (*(text + pos) == 0 || *(text + pos) == '\n')
            pos++;
    }

    return height;
}

void odroid_overlay_draw_rect(int x, int y, int width, int height, int border, uint16_t color)
{
    if (width == 0 || height == 0 || border == 0)
        return;

    int pixels = (width > height ? width : height) * border;
    for (int i = 0; i < pixels; i++)
        overlay_buffer[i] = color;
    odroid_display_write(x, y, width, border, overlay_buffer);                   // T
    odroid_display_write(x, y + height - border, width, border, overlay_buffer); // B
    odroid_display_write(x, y, border, height, overlay_buffer);                  // L
    odroid_display_write(x + width - border, y, border, height, overlay_buffer); // R
}

void odroid_overlay_draw_fill_rect(int x, int y, int width, int height, uint16_t color)
{
    if (width == 0 || height == 0)
        return;

    for (int i = 0; i < width * 16; i++)
        overlay_buffer[i] = color;

    int y_pos = y;
    int y_end = y + height;

    while (y_pos < y_end)
    {
        int thickness = (y_end - y_pos >= 16) ? 16 : (y_end - y_pos);
        odroid_display_write(x, y_pos, width, thickness, overlay_buffer);
        y_pos += 16;
    }
}

void gui_draw_header(tab_t *tab)
{

    odroid_overlay_draw_fill_rect(0, GW_LCD_HEIGHT - IMAGE_BANNER_HEIGHT - 15, GW_LCD_WIDTH, 32, curr_colors->main_c);

    if (tab->img_header)
        odroid_overlay_draw_logo(8, GW_LCD_HEIGHT - IMAGE_BANNER_HEIGHT - 15 + 7, (retro_logo_image *)(tab->img_header), curr_colors->sel_c);

    if (tab->img_logo) {
        retro_logo_image *img_logo = (retro_logo_image *)(tab->img_logo);
        int h = img_logo->height;
        h = (IMAGE_BANNER_HEIGHT - h) / 2;
        int w = h + img_logo->width;

        odroid_overlay_draw_logo(GW_LCD_WIDTH - w - 1,
                                 GW_LCD_HEIGHT - IMAGE_BANNER_HEIGHT - 15 + h,
                                 img_logo, get_shined_pixel(curr_colors->main_c, 25));
    }

    odroid_overlay_draw_fill_rect(0, GW_LCD_HEIGHT - 15, GW_LCD_WIDTH, 1, curr_colors->sel_c);
    odroid_overlay_draw_fill_rect(0, GW_LCD_HEIGHT - 13, GW_LCD_WIDTH, 4, curr_colors->main_c);
    odroid_overlay_draw_fill_rect(0, GW_LCD_HEIGHT - 10, GW_LCD_WIDTH, 2, curr_colors->bg_c);
    odroid_overlay_draw_fill_rect(0, GW_LCD_HEIGHT - 8, GW_LCD_WIDTH, 2, curr_colors->main_c);
    odroid_overlay_draw_fill_rect(0, GW_LCD_HEIGHT - 6, GW_LCD_WIDTH, 2, curr_colors->bg_c);
    odroid_overlay_draw_fill_rect(0, GW_LCD_HEIGHT - 4, GW_LCD_WIDTH, 1, curr_colors->main_c);
    odroid_overlay_draw_fill_rect(0, GW_LCD_HEIGHT - 3, GW_LCD_WIDTH, 2, curr_colors->bg_c);
    odroid_overlay_draw_fill_rect(0, GW_LCD_HEIGHT - 1, GW_LCD_WIDTH, 1, curr_colors->main_c);
}

void odroid_overlay_draw_logo(uint16_t x_pos, uint16_t y_pos, const retro_logo_image *logo, uint16_t color)
{
    uint16_t *dst_img = framebuffer;
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

static void draw_clock_digit(uint16_t *fb, const uint8_t clock, uint16_t px, uint16_t py, uint16_t color)
{
#if 0
    static const unsigned char *CLOCK_DIGITS[] = {img_clock_0, img_clock_1, img_clock_2, img_clock_3, img_clock_4, img_clock_5, img_clock_6, img_clock_7, img_clock_8, img_clock_9};
    const unsigned char *img = CLOCK_DIGITS[clock];
    for (uint8_t y = 0; y < 10; y++)
        for (uint8_t x = 0; x < 6; x++)
            if (img[y] & (1 << (7 - x)))
                fb[px + x + GW_LCD_WIDTH * (py + y)] = color;
#endif
};

void odroid_overlay_clock(int x_pos, int y_pos)
{
    uint16_t *dst_img = framebuffer;
    HAL_RTC_GetTime(&hrtc, &GW_currentTime, RTC_FORMAT_BIN);
    HAL_RTC_GetDate(&hrtc, &GW_currentDate, RTC_FORMAT_BIN);

    uint16_t color = get_darken_pixel(curr_colors->main_c, 75);
    draw_clock_digit(dst_img, 8, x_pos + 30, y_pos, color);
    draw_clock_digit(dst_img, 8, x_pos + 22, y_pos, color);
    draw_clock_digit(dst_img, 8, x_pos + 8, y_pos, color);
    draw_clock_digit(dst_img, 8, x_pos, y_pos, color);

    draw_clock_digit(dst_img, GW_currentTime.Minutes % 10, x_pos + 30, y_pos, curr_colors->sel_c);
    draw_clock_digit(dst_img, GW_currentTime.Minutes / 10, x_pos + 22, y_pos, curr_colors->sel_c);
    draw_clock_digit(dst_img, GW_currentTime.Hours % 10, x_pos + 8, y_pos, curr_colors->sel_c);
    draw_clock_digit(dst_img, GW_currentTime.Hours / 10, x_pos, y_pos, curr_colors->sel_c);

    color = (GW_currentTime.SubSeconds < 100) ? curr_colors->sel_c : get_darken_pixel(curr_colors->main_c, 75);
    odroid_overlay_draw_fill_rect(x_pos + 17, y_pos + 2, 2, 2, color);
    odroid_overlay_draw_fill_rect(x_pos + 17, y_pos + 6, 2, 2, color);
};

void gui_draw_status(tab_t *tab)
{
#if 0
    odroid_overlay_draw_fill_rect(0, 0, GW_LCD_WIDTH, STATUS_HEIGHT, curr_colors->main_c);
    odroid_overlay_draw_fill_rect(0, 1, GW_LCD_WIDTH, 2, curr_colors->bg_c);
    odroid_overlay_draw_fill_rect(0, 4, GW_LCD_WIDTH, 2, curr_colors->bg_c);
    odroid_overlay_draw_fill_rect(0, 8, GW_LCD_WIDTH, 2, curr_colors->bg_c);

    odroid_overlay_draw_logo(8, 16, (retro_logo_image *)(&logo_rgw), curr_colors->sel_c);

    odroid_overlay_clock(GW_LCD_WIDTH - 74, 17);
#endif
}
