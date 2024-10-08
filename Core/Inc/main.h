/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.h
  * @brief          : Header for main.c file.
  *                   This file contains the common defines of the application.
  ******************************************************************************
  * @attention
  *
  * <h2><center>&copy; Copyright (c) 2020 STMicroelectronics.
  * All rights reserved.</center></h2>
  *
  * This software component is licensed by ST under BSD 3-Clause license,
  * the "License"; You may not use this file except in compliance with the
  * License. You may obtain a copy of the License at:
  *                        opensource.org/licenses/BSD-3-Clause
  *
  ******************************************************************************
  */
/* USER CODE END Header */

/* Define to prevent recursive inclusion -------------------------------------*/
#ifndef __MAIN_H
#define __MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/
#include "stm32h7xx_hal.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* Exported types ------------------------------------------------------------*/
/* USER CODE BEGIN ET */

enum gnwmanager_sdcard_hw {
    GNWMANAGER_SDCARD_HW_UNDETECTED, // No detection done
    GNWMANAGER_SDCARD_HW_NO_SD_FOUND, // No SD detected
    GNWMANAGER_SDCARD_HW_1,           // Tim Schuerewegen design (SPI1)
    GNWMANAGER_SDCARD_HW_2,           // Yota9 design (soft SPI over OSPI)
};
typedef uint32_t gnwmanager_sdcard_hw_t;  // All computer interactions are uint32_t for simplicity.

extern gnwmanager_sdcard_hw_t sdcard_hw;
/* USER CODE END ET */

/* Exported constants --------------------------------------------------------*/
/* USER CODE BEGIN EC */
#ifdef HAL_ADC_MODULE_ENABLED
extern ADC_HandleTypeDef hadc1;
#endif
#ifdef HAL_DAC_MODULE_ENABLED
extern DAC_HandleTypeDef hdac1;
extern DAC_HandleTypeDef hdac2;
#endif
extern IWDG_HandleTypeDef hiwdg1;
extern LTDC_HandleTypeDef hltdc;
extern OSPI_HandleTypeDef hospi1;
extern RTC_HandleTypeDef hrtc;
#ifdef HAL_SAI_MODULE_ENABLED
extern SAI_HandleTypeDef hsai_BlockA1;
extern DMA_HandleTypeDef hdma_sai1_a;
#endif
extern SPI_HandleTypeDef hspi1;
extern SPI_HandleTypeDef hspi2;
extern TIM_HandleTypeDef htim1;
extern HASH_HandleTypeDef hhash;

/* USER CODE END EC */

/* Exported macro ------------------------------------------------------------*/
/* USER CODE BEGIN EM */

/* USER CODE END EM */

/* Exported functions prototypes ---------------------------------------------*/
void Error_Handler(void);

/* USER CODE BEGIN EFP */
void wdog_refresh(void);
void MX_SPI1_Init(void);
/* USER CODE END EFP */

/* Private defines -----------------------------------------------------------*/
#define GPIO_Speaker_enable_Pin GPIO_PIN_3
#define GPIO_Speaker_enable_GPIO_Port GPIOE
#define BTN_PAUSE_Pin GPIO_PIN_13
#define BTN_PAUSE_GPIO_Port GPIOC
#define BTN_GAME_Pin GPIO_PIN_1
#define BTN_GAME_GPIO_Port GPIOC
#define BTN_PWR_Pin GPIO_PIN_0
#define BTN_PWR_GPIO_Port GPIOA
#define BACKLIGHT_RIGHT_Pin GPIO_PIN_4
#define BACKLIGHT_RIGHT_GPIO_Port GPIOA
#define BACKLIGHT_MIDDLE_Pin GPIO_PIN_5
#define BACKLIGHT_MIDDLE_GPIO_Port GPIOA
#define BACKLIGHT_LEFT_Pin GPIO_PIN_6
#define BACKLIGHT_LEFT_GPIO_Port GPIOA
#define BTN_TIME_Pin GPIO_PIN_5
#define BTN_TIME_GPIO_Port GPIOC
#define BATMAN_CE_Pin GPIO_PIN_8
#define BATMAN_CE_GPIO_Port GPIOE
#define LCD_Reset_Pin GPIO_PIN_8
#define LCD_Reset_GPIO_Port GPIOD
#define BTN_A_Pin GPIO_PIN_9
#define BTN_A_GPIO_Port GPIOD
#define BTN_Left_Pin GPIO_PIN_11
#define BTN_Left_GPIO_Port GPIOD
#define BTN_Down_Pin GPIO_PIN_14
#define BTN_Down_GPIO_Port GPIOD
#define BTN_Right_Pin GPIO_PIN_15
#define BTN_Right_GPIO_Port GPIOD
#define BTN_START_Pin GPIO_PIN_11
#define BTN_START_GPIO_Port GPIOC
#define BTN_SELECT_Pin GPIO_PIN_12
#define BTN_SELECT_GPIO_Port GPIOC
#define BTN_Up_Pin GPIO_PIN_0
#define BTN_Up_GPIO_Port GPIOD
#define VAUX_Enable_Pin GPIO_PIN_1
#define VAUX_Enable_GPIO_Port GPIOD
#define V3V3_Enable_Pin GPIO_PIN_4
#define V3V3_Enable_GPIO_Port GPIOD
#define BTN_B_Pin GPIO_PIN_5
#define BTN_B_GPIO_Port GPIOD
/* USER CODE BEGIN Private defines */

// SPI1 pins
#define SD_VCC_GPIO_Port GPIOA
#define SD_VCC_Pin GPIO_PIN_15
#define SD_CS_GPIO_Port GPIOB
#define SD_CS_Pin GPIO_PIN_9

// OSPI1 pins
#define GPIO_FLASH_NCS_Pin GPIO_PIN_11
#define GPIO_FLASH_NCS_GPIO_Port GPIOE
#define GPIO_FLASH_MOSI_Pin GPIO_PIN_1
#define GPIO_FLASH_MOSI_GPIO_Port GPIOB
#define GPIO_FLASH_CLK_Pin GPIO_PIN_2
#define GPIO_FLASH_CLK_GPIO_Port GPIOB
#define GPIO_FLASH_MISO_Pin GPIO_PIN_12
#define GPIO_FLASH_MISO_GPIO_Port GPIOD

/* USER CODE END Private defines */

#ifdef __cplusplus
}
#endif

#endif /* __MAIN_H */

/************************ (C) COPYRIGHT STMicroelectronics *****END OF FILE****/
