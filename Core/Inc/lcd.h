#ifndef _LCD_H_
#define _LCD_H_

#include "stm32h7xx_hal.h"
#include <stdint.h>

typedef uint16_t pixel_t;

#define GW_LCD_WIDTH  320
#define GW_LCD_HEIGHT 240

extern pixel_t framebuffer[GW_LCD_WIDTH * GW_LCD_HEIGHT]  __attribute__((section (".lcd")));

void lcd_init(SPI_HandleTypeDef *spi, LTDC_HandleTypeDef *ltdc);
void lcd_deinit(SPI_HandleTypeDef *spi);
void lcd_backlight_on();
void lcd_backlight_off();
void lcd_wait_for_vblank(void);
uint32_t lcd_get_frame_counter(void);

#endif
