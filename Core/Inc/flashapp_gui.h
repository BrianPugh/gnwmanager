#pragma once

#define RGB24_TO_RGB565(r, g, b) ( ((r) >> 3) << 11 ) | ( ((g) >> 2) << 5 ) | ( (b) >> 3 )


void flashapp_gui_draw();
