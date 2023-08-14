#pragma once

#define _2C_(C) (((C >> 8) & 0xF800) | ((C >> 5) & 0x7E0) | ((C >> 3) & 0x1F))

void flashapp_gui_draw();
