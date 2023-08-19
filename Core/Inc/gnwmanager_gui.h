#pragma once

#include "gnwmanager.h"
#include <float.h>

#define RGB24_TO_RGB565(r, g, b) ( ((r) >> 3) << 11 ) | ( ((g) >> 2) << 5 ) | ( (b) >> 3 )

typedef struct{
    volatile gnwmanager_status_t *status;
    volatile uint32_t *progress;

    uint8_t sleep_z_state;  // [0, 3]
    uint8_t counter_to_sleep;

    uint8_t run_state;  // [0, 9]
} gnwmanager_gui_t;

extern gnwmanager_gui_t gui;

void gnwmanager_gui_draw(bool step);
