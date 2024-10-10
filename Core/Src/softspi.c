#include <stdbool.h>

#include "softspi.h"
#include "main.h"

__attribute__((always_inline)) static inline void gpio_pause()
{
    __asm("NOP");
    __asm("NOP");
    __asm("NOP");
    __asm("NOP");
    __asm("NOP");
    __asm("NOP");
    __asm("NOP");
    __asm("NOP");
    __asm("NOP");
    __asm("NOP");
    __asm("NOP");
    __asm("NOP");
    __asm("NOP");
    __asm("NOP");
    __asm("NOP");
    __asm("NOP");
}

static void delay_us(uint32_t usec)
{
    uint32_t cycles_per_us = SystemCoreClock / 1000000;
    uint32_t nop_count = cycles_per_us * (usec / 2);

    while (nop_count--)
    {
        __asm("NOP");
    }
}

static void __SoftSpi_WriteRead(SoftSPI *spi, const uint8_t *txData, uint8_t *rxData,
                                uint32_t len, bool txDummy, bool csEnable)
{
    int i, j;
    uint8_t txBit, rxBit;
    uint8_t txByte, rxByte;

    if (!len)
        return;

    HAL_GPIO_WritePin(spi->sck.port, spi->sck.pin, GPIO_PIN_RESET);
    if (csEnable)
        HAL_GPIO_WritePin(spi->cs.port, spi->cs.pin,
                          spi->csIsInverted ? GPIO_PIN_SET : GPIO_PIN_RESET);
    else if (spi->cs.port)
        HAL_GPIO_WritePin(spi->cs.port, spi->cs.pin,
                          spi->csIsInverted ? GPIO_PIN_RESET : GPIO_PIN_SET);

    for (i = 0; i < len; i++)
    {
        txByte = txDummy ? txData[0] : txData[i];
        rxByte = 0;

        for (j = 7; j >= 0; j--)
        {
            txBit = (txByte & (1 << j)) ? 1 : 0;

            HAL_GPIO_WritePin(spi->mosi.port, spi->mosi.pin, txBit ? GPIO_PIN_SET : GPIO_PIN_RESET);
            gpio_pause();
            HAL_GPIO_WritePin(spi->sck.port, spi->sck.pin, GPIO_PIN_SET);
            delay_us(spi->DelayUs);

            rxBit = HAL_GPIO_ReadPin(spi->miso.port, spi->miso.pin) == GPIO_PIN_SET ? 1 : 0;
            rxByte <<= 1;
            rxByte |= rxBit;

            HAL_GPIO_WritePin(spi->sck.port, spi->sck.pin, GPIO_PIN_RESET);
            delay_us(spi->DelayUs);
        }

        if (rxData)
            rxData[i] = rxByte;
    }

    if (csEnable)
        HAL_GPIO_WritePin(spi->cs.port, spi->cs.pin,
                          spi->csIsInverted ? GPIO_PIN_RESET : GPIO_PIN_SET);
}

void SoftSpi_WriteRead(SoftSPI *spi, const uint8_t *txData, uint8_t *rxData, uint32_t len)
{
    __SoftSpi_WriteRead(spi, txData, rxData, len, false, !!spi->cs.port);
}

void SoftSpi_WriteDummyRead(SoftSPI *spi, uint8_t *rxData, uint32_t len)
{
    uint8_t dummy = 0xFF;
    __SoftSpi_WriteRead(spi, &dummy, rxData, len, true, !!spi->cs.port);
}

void SoftSpi_WriteDummyReadCsLow(SoftSPI *spi, uint8_t *rxData, uint32_t len)
{
    uint8_t dummy = 0xFF;
    __SoftSpi_WriteRead(spi, &dummy, rxData, len, true, false);
}
