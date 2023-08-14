#pragma once

#include "flashapp.h"

#define RGB24_TO_RGB565(r, g, b) ( ((r) >> 3) << 11 ) | ( ((g) >> 2) << 5 ) | ( (b) >> 3 )

typedef struct{
    flashapp_status_t *status;
} flashapp_gui_state_t;

void flashapp_gui_draw();
