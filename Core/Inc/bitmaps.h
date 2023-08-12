#pragma once
#include <stdint.h>

typedef struct
{
    uint32_t width;
    uint32_t height;
    const char logo[];
} retro_logo_image;

extern const retro_logo_image logo_rgw;
extern const retro_logo_image logo_gnw;
extern const retro_logo_image logo_flash;

extern const unsigned char img_clock_00[];
extern const unsigned char img_clock_01[];
extern const unsigned char img_clock_02[];
extern const unsigned char img_clock_03[];
extern const unsigned char img_clock_04[];
extern const unsigned char img_clock_05[];
extern const unsigned char img_clock_06[];
extern const unsigned char img_clock_07[];
extern const unsigned char img_clock_08[];
extern const unsigned char img_clock_09[];
