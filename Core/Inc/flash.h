#pragma once

#include "stm32h7xx_hal.h"

#include <stdint.h>
#include <stdbool.h>


void OSPI_EnableMemoryMappedMode(void);
void OSPI_DisableMemoryMappedMode(void);
void OSPI_ChipErase(bool blocking);
bool OSPI_ChipIdle();

// Performs one erase command per call with the largest size possible.
// Sets *address and *size to values that should be passed to
// OSPI_Erase in the next iteration.
// Returns true when done.
bool OSPI_Erase(uint32_t *address, uint32_t *size, bool blocking);

// Erases the area synchronously. Will block until it's done.
void OSPI_EraseSync(uint32_t address, uint32_t size);

void OSPI_PageProgram(uint32_t address, const uint8_t *buffer, size_t buffer_size);
void OSPI_NOR_WriteEnable(void);
void OSPI_Program(uint32_t address, const uint8_t *buffer, size_t buffer_size);

void OSPI_ReadJedecId(uint8_t dest[3]);
void OSPI_ReadSR(uint8_t dest[1]);
void OSPI_ReadCR(uint8_t dest[1]);
const char* OSPI_GetFlashName(void);
uint32_t OSPI_GetSmallestEraseSize(void);

int OSPI_Init(OSPI_HandleTypeDef *hospi);

uint32_t OSPI_GetSize(void);
