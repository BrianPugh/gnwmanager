#include <stdbool.h>
#include "sdcard.h"
#include "main.h"
#include "timer.h"

void sdcard_init_spi1() {
        // PeriphClkInitStruct.PeriphClockSelection = RCC_PERIPHCLK_SPI1 should be set
    // but as it's common with SPI2, it's already selected
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    /*Configure GPIO pin Output Level */
    /* PA15 = 0v : Disable SD Card VCC */
    HAL_GPIO_WritePin(SD_VCC_GPIO_Port, SD_VCC_Pin, GPIO_PIN_RESET);

    /*Configure GPIO pin Output Level */
    /* PB9 = 0v : SD Card disable CS  */
    HAL_GPIO_WritePin(SD_CS_GPIO_Port, SD_CS_Pin, GPIO_PIN_SET);

    /*Configure GPIO pin : PA15 to control SD Card VCC */
    GPIO_InitStruct.Pin = SD_VCC_Pin;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(SD_VCC_GPIO_Port, &GPIO_InitStruct);

    /*Configure GPIO pin : PB9 SD Card CS */
    GPIO_InitStruct.Pin = GPIO_PIN_9;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

    // Reset sd card by setting VCC to 0 for 5ms
    timer_on(0, 5); 
    while (timer_status(0));
    /* PA15 = 0v : Enable SD Card VCC */
    HAL_GPIO_WritePin(SD_VCC_GPIO_Port, SD_VCC_Pin, GPIO_PIN_SET);

    MX_SPI1_Init();

    HAL_SPI_MspInit(&hspi1);    
}

void sdcard_deinit_spi1() {
    HAL_GPIO_WritePin(SD_VCC_GPIO_Port, SD_VCC_Pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(SD_CS_GPIO_Port, SD_CS_Pin, GPIO_PIN_RESET);

    HAL_SPI_MspDeInit(&hspi1);
}

void sdcard_init_ospi1() {
    HAL_NVIC_DisableIRQ(OCTOSPI1_IRQn);
}

void sdcard_deinit_ospi1() {
    HAL_NVIC_EnableIRQ(OCTOSPI1_IRQn);
}

void switch_ospi_gpio(uint8_t ToOspi) {
  static uint8_t IsOspi = true;
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  if (IsOspi == ToOspi)
    return;

  if (ToOspi) {
    if (HAL_OSPI_Init(&hospi1) != HAL_OK)
      Error_Handler();
  } else {
    HAL_OSPI_DeInit(&hospi1);

    /*Configure GPIO pin Output Level */
    HAL_GPIO_WritePin(GPIOE, GPIO_FLASH_NCS_Pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(GPIOB, GPIO_FLASH_MOSI_Pin|GPIO_FLASH_CLK_Pin, GPIO_PIN_RESET);

    /*Configure GPIO pin : GPIO_FLASH_NCS_Pin */
    GPIO_InitStruct.Pin = GPIO_FLASH_NCS_Pin;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
    HAL_GPIO_Init(GPIO_FLASH_NCS_GPIO_Port, &GPIO_InitStruct);

    /*Configure GPIO pins : GPIO_FLASH_MOSI_Pin GPIO_FLASH_CLK_Pin */
    GPIO_InitStruct.Pin = GPIO_FLASH_MOSI_Pin|GPIO_FLASH_CLK_Pin;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

    /*Configure GPIO pins : GPIO_FLASH_MISO_Pin */
    GPIO_InitStruct.Pin = GPIO_FLASH_MISO_Pin;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(GPIO_FLASH_MISO_GPIO_Port, &GPIO_InitStruct);
  }

  IsOspi = ToOspi;
}