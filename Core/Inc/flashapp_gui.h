#pragma once

#include "flashapp.h"
#include <float.h>

#define RGB24_TO_RGB565(r, g, b) ( ((r) >> 3) << 11 ) | ( ((g) >> 2) << 5 ) | ( (b) >> 3 )

typedef struct{
    flashapp_status_t *status;
    float percent_complete;
} flashapp_gui_t;

void flashapp_gui_draw(flashapp_gui_t *);
