#include "lcd.h"
#include "stm32h7xx_hal.h"
#include "main.h"

pixel_t framebuffer[320 * 240] __attribute__((section (".lcd")));
static uint32_t frame_counter;
extern LTDC_HandleTypeDef hltdc;


void lcd_backlight_off() {
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_4, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_5, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_6, GPIO_PIN_RESET);
}

void lcd_backlight_on() {
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_4, GPIO_PIN_SET);
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_5, GPIO_PIN_SET);
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_6, GPIO_PIN_SET);
}


static void gw_set_power_1V8(uint32_t p) {
  HAL_GPIO_WritePin(GPIOD, GPIO_PIN_1, p == 0 ? GPIO_PIN_SET : GPIO_PIN_RESET);
}
static void gw_set_power_3V3(uint32_t p) {
  HAL_GPIO_WritePin(GPIOD, GPIO_PIN_4, p == 1 ? GPIO_PIN_SET : GPIO_PIN_RESET);
}
static void gw_lcd_set_chipselect(uint32_t p) {
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_12, p == 0 ? GPIO_PIN_SET : GPIO_PIN_RESET);
}
static void gw_lcd_set_reset(uint32_t p) {
  HAL_GPIO_WritePin(GPIOD, GPIO_PIN_8, p == 0 ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

static void gw_lcd_spi_tx(SPI_HandleTypeDef *spi, uint8_t *pData) {
  gw_lcd_set_chipselect(1);
  HAL_Delay(2);
  HAL_SPI_Transmit(spi, pData, 2, 100);
  HAL_Delay(2);
  wdog_refresh();
  gw_lcd_set_chipselect(0);
  HAL_Delay(2);
}

void lcd_deinit(SPI_HandleTypeDef *spi) {
  // Power off
  gw_set_power_1V8(0);
  gw_set_power_3V3(0);
}

void lcd_init(SPI_HandleTypeDef *spi, LTDC_HandleTypeDef *ltdc) {
  // Disable LCD Chip select
  gw_lcd_set_chipselect(0);

  // LCD reset
  gw_lcd_set_reset(0);

  // Wake up !
  // Enable 1.8V &3V3 power supply
  gw_set_power_3V3(1);
  HAL_Delay(2);
  gw_set_power_1V8(1);
  HAL_Delay(50);
  wdog_refresh();

  // Lets go, bootup sequence.
  /* reset sequence */
  gw_lcd_set_reset(0);
  HAL_Delay(1);
  gw_lcd_set_reset(1);
  HAL_Delay(20);
  gw_lcd_set_reset(0);
  HAL_Delay(50);
  wdog_refresh();

  gw_lcd_spi_tx(spi, (uint8_t *)"\x08\x80");
  gw_lcd_spi_tx(spi, (uint8_t *)"\x6E\x80");
  gw_lcd_spi_tx(spi, (uint8_t *)"\x80\x80");

  gw_lcd_spi_tx(spi, (uint8_t *)"\x68\x00");
  gw_lcd_spi_tx(spi, (uint8_t *)"\xd0\x00");
  gw_lcd_spi_tx(spi, (uint8_t *)"\x1b\x00");
  gw_lcd_spi_tx(spi, (uint8_t *)"\xe0\x00");

  gw_lcd_spi_tx(spi, (uint8_t *)"\x6a\x80");
  gw_lcd_spi_tx(spi, (uint8_t *)"\x80\x00");
  gw_lcd_spi_tx(spi, (uint8_t *)"\x14\x80");
  wdog_refresh();

  HAL_LTDC_SetAddress(ltdc,(uint32_t) framebuffer, 0);

  memset(framebuffer, 0, sizeof(framebuffer));

  __HAL_LTDC_ENABLE_IT(&hltdc, LTDC_IT_LI | LTDC_IT_RR);
  HAL_LTDC_ProgramLineEvent(&hltdc, 239);
}

void HAL_LTDC_LineEventCallback (LTDC_HandleTypeDef *hltdc) {
  frame_counter++;
  HAL_LTDC_ProgramLineEvent(hltdc,  239);
}

void lcd_wait_for_vblank(void)
{
  uint32_t old_counter = frame_counter;
  while (old_counter == frame_counter) {
    __asm("nop");
  }
}
