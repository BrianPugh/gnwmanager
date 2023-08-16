#pragma once

#include "flashapp.h"
#include <float.h>

#define RGB24_TO_RGB565(r, g, b) ( ((r) >> 3) << 11 ) | ( ((g) >> 2) << 5 ) | ( (b) >> 3 )

typedef struct{
    volatile flashapp_status_t *status;
    volatile uint32_t *progress;

    uint8_t sleep_z_state;  // [0, 3]
    uint8_t sleeping;

    uint8_t run_state;  // [0, 9]
    bool running;
} flashapp_gui_t;

extern flashapp_gui_t gui;

void flashapp_gui_draw(bool step);
