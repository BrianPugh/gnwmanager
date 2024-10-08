/**
 ******************************************************************************
 * @file    user_diskio_spi.c
 * @brief   This file contains the implementation of the user_diskio_spi FatFs
 *          driver.
 ******************************************************************************
 * Portions copyright (C) 2014, ChaN, all rights reserved.
 * Portions copyright (C) 2017, kiwih, all rights reserved.
 *
 * This software is a free software and there is NO WARRANTY.
 * No restriction on use. You can use, modify and redistribute it for
 * personal, non-profit or commercial products UNDER YOUR RESPONSIBILITY.
 * Redistributions of source code must retain the above copyright notice.
 *
 ******************************************************************************
 */

// This code was ported by kiwih from a copywrited (C) library written by ChaN
// available at http://elm-chan.org/fsw/ff/ffsample.zip
//(text at http://elm-chan.org/fsw/ff/00index_e.html)

// This file provides the FatFs driver functions and SPI code required to manage
// an SPI-connected MMC or compatible SD card with FAT

// It is designed to be wrapped by a cubemx generated user_diskio.c file.

#include "main.h"
#include "stm32h7xx_hal.h" /* Provide the low-level HAL functions */
#include "user_diskio_spi.h"
#include "sdcard.h"
#include "softspi.h"
#include "timer.h"

static volatile DSTATUS Stat = STA_NOINIT; /* Disk Status */
static uint8_t CardType;                   /* Type 0:MMC, 1:SDC, 2:Block addressing */
static uint8_t PowerFlag = 0;              /* Power flag */

#ifndef MIN
#define MIN(a, b) ({__typeof__(a) _a = (a); __typeof__(b) _b = (b);_a < _b ? _a : _b; })
#endif // !MIN

#define BLOCK_SIZE 512ULL

static struct
{
    SoftSPI spi[1];
    bool isSdV2 : 1;
    bool ccs : 1;
} sd = {
    .spi[0] = {
        .sck = {.port = GPIO_FLASH_CLK_GPIO_Port, .pin = GPIO_FLASH_CLK_Pin},
        .mosi = {.port = GPIO_FLASH_MOSI_GPIO_Port, .pin = GPIO_FLASH_MOSI_Pin},
        .miso = {.port = GPIO_FLASH_MISO_GPIO_Port, .pin = GPIO_FLASH_MISO_Pin},
        .cs = {.port = GPIO_FLASH_NCS_GPIO_Port, .pin = GPIO_FLASH_NCS_Pin},
        .DelayUs = 20,
        .csIsInverted = true}};

static void FCLK_SLOW()
{
    sd.spi->DelayUs = 20;
}

static void FCLK_FAST()
{
    sd.spi->DelayUs = 0;
}

//-----[ SPI Functions ]-----
/* slave select */
static void SELECT(void)
{
}

/* slave deselect */
static void DESELECT(void)
{
}

// =============================================================================
// SD card responses
// =============================================================================

#define START_BLOCK_TOKEN 0xFE

typedef bool (*response_fn)(uint8_t *r);

#define R1_IDLE 0ULL
#define R1_ERASE_RESET 1ULL
#define R1_ILLEGAL_COMMAND 2ULL
#define R1_CRC_ERROR 3ULL
#define R1_ERASE_SEQUENCE_ERROR 4ULL
#define R1_ADDRESS_ERROR 5ULL
#define R1_PARAMETER_ERROR 6ULL
#define R1_ALWAYS_ZERO 7ULL

static bool responseR1(uint8_t *r)
{
    *r = 0xFF;
    for (int i = 0; i < 10 && *r == 0xFF; ++i)
        SoftSpi_WriteDummyRead(sd.spi, r, sizeof(*r));

    return *r != 0xFF;
}

#define R2_CARD_LOCKED 0ULL
#define R2_WP_ERASE_SKIP 1ULL
#define R2_ERROR 2ULL
#define R2_CC_ERROR 3ULL
#define R2_CARD_ECC_FAILED 4ULL
#define R2_WP_VIOLATION 5ULL
#define R2_ERASE_PARAM 6ULL
#define R2_OUT_OF_RANGE 7ULL

#define R2_GET_R1(r) (((uint8_t *)r)[1])

__attribute__((unused)) static bool responseR2(uint8_t *r)
{
    if (!responseR1((uint8_t *)&(R2_GET_R1(r))))
        return false;

    SoftSpi_WriteDummyRead(sd.spi, &r[0], sizeof(*r));
    return !r[1] || r[1] == (1 << R1_IDLE);
}

#define R3_V27_28 15ULL
#define R3_V28_29 16ULL
#define R3_V29_30 17ULL
#define R3_V30_31 18ULL
#define R3_V31_32 19ULL
#define R3_V32_33 20ULL
#define R3_V33_34 21ULL
#define R3_V34_35 22ULL
#define R3_V35_36 23ULL
#define R3_V18 24ULL
#define R3_UHS2 29ULL
#define R3_CCS 30ULL
#define R3_READY 31ULL

#define R3R7_GET_R1(r) (((uint8_t *)r)[4])

static bool responseR3R7(uint8_t *r)
{
    if (!responseR1(&(R3R7_GET_R1(r))))
        return false;

    SoftSpi_WriteDummyRead(sd.spi, &r[3], sizeof(*r));
    SoftSpi_WriteDummyRead(sd.spi, &r[2], sizeof(*r));
    SoftSpi_WriteDummyRead(sd.spi, &r[1], sizeof(*r));
    SoftSpi_WriteDummyRead(sd.spi, &r[0], sizeof(*r));
    return !r[4] || r[4] == (1 << R1_IDLE);
}

static bool responseCMD8(uint8_t *r)
{
    if (responseR3R7(r))
        return true;

    // Old v1 sd card, fault is expected
    if (r[4] & (1 << R1_ILLEGAL_COMMAND))
        return true;

    return false;
}

static bool responseCMD12(uint8_t *r)
{
    *r = 0xFF;
    /* Skip a stuff byte when STOP_TRANSMISSION */
    SoftSpi_WriteDummyRead(sd.spi, NULL, 1);
    for (int i = 0; i < 10 && *r == 0xFF; ++i)
        SoftSpi_WriteDummyRead(sd.spi, r, sizeof(*r));

    return *r != 0xFF;
}

struct response
{
    uint64_t r0;
};

// =============================================================================
// SD card commands
// =============================================================================

#define SD_GO_IDLE_STATE_CMD 0
#define SD_SEND_OP_COND_CMD 1
#define SD_SEND_INTERFACE_COND_CMD 8
#define SD_STOP_TRANSMISSION_CMD 12
#define SD_READ_SINGLE_BLOCK_CMD 17
#define SD_READ_MULTIPLE_BLOCK_CMD 18
#define SD_WRITE_SINGLE_BLOCK_CMD 24
#define SD_WRITE_MULTIPLE_BLOCK_CMD 25
#define SD_SEND_OP_COND_ACMD 41
#define SD_APP_CMD 55
#define SD_READ_OCR_CMD 58

enum cmd_list
{
    GO_IDLE_STATE = 0,
    SEND_OP_COND,
    SEND_INTERFACE_COND,
    SEND_STOP_TRANSMISSION,
    READ_SINGLE_BLOCK,
    READ_MULTIPLE_BLOCK,
    WRITE_SINGLE_BLOCK,
    WRITE_MULTIPLE_BLOCK,
    SEND_OP_COND_ACMD,
    APP_CMD,
    READ_OCR,
};

static struct sd_cmd
{
    uint8_t cmd;
    uint8_t crc;
    response_fn response;
} sd_cmds[] = {
    [GO_IDLE_STATE] = {SD_GO_IDLE_STATE_CMD, 0x95, responseR1},
    [SEND_OP_COND] = {SD_SEND_OP_COND_CMD, 0x0, responseR1},
    [SEND_INTERFACE_COND] = {SD_SEND_INTERFACE_COND_CMD, 0x86, responseCMD8},
    [SEND_STOP_TRANSMISSION] = {SD_STOP_TRANSMISSION_CMD, 0x00, responseCMD12},
    [READ_SINGLE_BLOCK] = {SD_READ_SINGLE_BLOCK_CMD, 0x0, responseR1},
    [READ_MULTIPLE_BLOCK] = {SD_READ_MULTIPLE_BLOCK_CMD, 0x0, responseR1},
    [WRITE_SINGLE_BLOCK] = {SD_WRITE_SINGLE_BLOCK_CMD, 0x0, responseR1},
    [WRITE_MULTIPLE_BLOCK] = {SD_WRITE_MULTIPLE_BLOCK_CMD, 0x0, responseR1},
    [SEND_OP_COND_ACMD] = {SD_SEND_OP_COND_ACMD, 0x0, responseR1},
    [APP_CMD] = {SD_APP_CMD, 0x0, responseR1},
    [READ_OCR] = {SD_READ_OCR_CMD, 0x0, responseR3R7},
};

// =============================================================================

static void __send_cmd_payload(uint8_t cmd, uint32_t arg, uint32_t crc)
{
    uint8_t spi_cmd_payload[6] = {cmd | 0x40, arg >> 24, arg >> 16, arg >> 8, arg, crc | 0x1};
    SoftSpi_WriteDummyRead(sd.spi, NULL, 2);
    SoftSpi_WriteRead(sd.spi, spi_cmd_payload, NULL, sizeof(spi_cmd_payload));
    wdog_refresh();
}

static bool __send_cmd(enum cmd_list cmd, uint32_t arg, struct response *response)
{
    __send_cmd_payload(sd_cmds[cmd].cmd, arg, sd_cmds[cmd].crc);
    return sd_cmds[cmd].response((uint8_t *)response);
}

static struct response send_cmd(enum cmd_list cmd, uint32_t arg)
{
    struct response response = {};
    for (int i = 0; i < 10; i++)
    {
        if (__send_cmd(cmd, arg, &response))
            return response;
    }

    return response;
}

static void finish_read_cmd(void)
{
    // Skip checksum reading
    SoftSpi_WriteDummyRead(sd.spi, NULL, 2);
}

static bool finish_write_cmd(void)
{
    uint8_t rbyte;

    // Dummy crc
    SoftSpi_WriteDummyRead(sd.spi, NULL, 2);

    // We would fail on watchdog if something is wrong here
    // Read status byte
    do
    {
        SoftSpi_WriteDummyRead(sd.spi, &rbyte, 1);
    } while (rbyte == 0xFF); // Fix : add timeout

    if ((rbyte & 0xF) != 0x05)
    {
        return false;
    }

    // Wait for data to be written
    do
    {
        SoftSpi_WriteDummyRead(sd.spi, &rbyte, 1);
    } while (rbyte == 0x00); // Fix : add timeout

    return true;
}

//-----[ SD Card Functions ]-----

/* wait SD ready */
static uint8_t SD_ReadyWait(void)
{
    uint8_t res;
    /* timeout 500ms */
    timer_on(1, 500);
    /* if SD goes ready, receives 0xFF */
    do
    {
        wdog_refresh();
        SoftSpi_WriteDummyRead(sd.spi, &res, 1);
    } while ((res != 0xFF) && timer_status(1));
    return res;
}

/* power on */
static bool SD_PowerOn(void)
{
    struct response response;

    SoftSpi_WriteDummyReadCsLow(sd.spi, NULL, 10);

    response = send_cmd(GO_IDLE_STATE, 0);
    if (response.r0 != (1 << R1_IDLE))
    {
        switch_ospi_gpio(true);
        return false;
    }

    DESELECT();
    PowerFlag = 1;
    return true; // Sylver
}

/* power off */
static void SD_PowerOff(void)
{
    PowerFlag = 0;
}

/* check power flag */
static uint8_t SD_CheckPower(void)
{
    return PowerFlag;
}

/*--------------------------------------------------------------------------

   Public FatFs Functions (wrapped in user_diskio.c)

---------------------------------------------------------------------------*/

// The following functions are defined as inline because they aren't the functions that
// are passed to FatFs - they are wrapped by autogenerated (non-inline) cubemx template
// code.
// If you do not wish to use cubemx, remove the "inline" from these functions here
// and in the associated .h

/*-----------------------------------------------------------------------*/
/* Initialize disk drive                                                 */
/*-----------------------------------------------------------------------*/

DSTATUS USER_SOFTSPI_initialize(
    BYTE drv /* Physical drive number (0) */
)
{
    struct response response;
    int i;

    /* single drive, drv should be 0 */
    if (drv)
        return STA_NOINIT;
    /* no disk */
    if (Stat & STA_NODISK)
        return Stat;

    switch_ospi_gpio(false);

    /* power on */
    if (!SD_PowerOn()) {
        return STA_NOINIT;
    }
    /* slave select */
    SELECT();

    FCLK_SLOW();

    // 3.3V + AA pattern
    response = send_cmd(SEND_INTERFACE_COND, 0x1AA);
    sd.isSdV2 = !(R3R7_GET_R1(&response) == (1 << R1_ILLEGAL_COMMAND));
    if (sd.isSdV2)
    {
        CardType = CT_SD2;
    }
    else
    {
        CardType = CT_SD1;
    }

    // Needed by manual
    send_cmd(READ_OCR, 0);

    for (i = 0; i < 255; i++)
    {
        if (sd.isSdV2)
        {
            response = send_cmd(APP_CMD, 0);
            if (response.r0 && response.r0 != (1 << R1_IDLE))
                continue;

            // High capacity card support
            response = send_cmd(SEND_OP_COND_ACMD, 0x40000000);
            if (!response.r0)
                break;
        }
        else
        {
            response = send_cmd(SEND_OP_COND, 0);
            if (!response.r0)
                break;
        }
    }

    if (i == 255)
    {
        return STA_NOINIT;
    }

    if (sd.isSdV2)
    {
        response = send_cmd(READ_OCR, 0);
        if (!(response.r0 & (1 << R3_READY)))
        {
            return STA_NOINIT;
        }

        sd.ccs = response.r0 & (1 << R3_CCS);
        if (sd.ccs)
            CardType |= CT_BLOCK;
    }

    /* Idle */
    DESELECT();

    /* Clear STA_NOINIT */
    if (CardType)
    {
        FCLK_FAST();
        Stat &= ~STA_NOINIT;
    }
    else
    {
        /* Initialization failed */
        SD_PowerOff();
    }
    switch_ospi_gpio(true);

    return Stat;
}

/*-----------------------------------------------------------------------*/
/* Get disk status                                                       */
/*-----------------------------------------------------------------------*/

DSTATUS USER_SOFTSPI_status(
    BYTE drv /* Physical drive number (0) */
)
{
    if (drv)
        return STA_NOINIT; /* Supports only drive 0 */

    return Stat; /* Return disk status */
}

/*-----------------------------------------------------------------------*/
/* Read sector(s)                                                        */
/*-----------------------------------------------------------------------*/

DRESULT USER_SOFTSPI_read(
    BYTE pdrv,    /* Physical drive number (0) */
    BYTE *buff,   /* Pointer to the data buffer to store read data */
    DWORD sector, /* Start sector number (LBA) */
    UINT count    /* Number of sectors to read (1..128) */
)
{
    uint8_t ret;
    /* pdrv should be 0 */
    if (pdrv || !count)
        return RES_PARERR;

    /* no disk */
    if (Stat & STA_NOINIT)
        return RES_NOTRDY;

    /* convert to byte address */
    if (!(CardType & CT_BLOCK))
        sector *= 512;

    switch_ospi_gpio(false);

    SELECT();

    if (count == 1)
    {
        /* READ_SINGLE_BLOCK */
        if (send_cmd(READ_SINGLE_BLOCK, sector).r0)
        {
            return RES_ERROR;
        }

        // We would fail on watchdog if something is wrong here
        do
        {
            SoftSpi_WriteDummyRead(sd.spi, &ret, 1);
        } while (ret != START_BLOCK_TOKEN); // Fix : add timeout

        SoftSpi_WriteDummyRead(sd.spi, buff, BLOCK_SIZE);

        finish_read_cmd();
        count = 0;
    }
    else
    {
        if (send_cmd(READ_MULTIPLE_BLOCK, sector).r0)
        {
            return RES_ERROR;
        }
        // We would fail on watchdog if something is wrong here
        do
        {
            SoftSpi_WriteDummyRead(sd.spi, &ret, 1);
        } while (ret != START_BLOCK_TOKEN);

        do
        {
            SoftSpi_WriteDummyRead(sd.spi, buff, BLOCK_SIZE);
            /* discard CRC */
            SoftSpi_WriteDummyRead(sd.spi, NULL, 10);
            buff += 512;
        } while (--count);

        /* STOP_TRANSMISSION */
        send_cmd(SEND_STOP_TRANSMISSION, 0);
    }

    /* Idle */
    DESELECT();
    SD_ReadyWait();
    switch_ospi_gpio(true);

    return count ? RES_ERROR : RES_OK;
}

/*-----------------------------------------------------------------------*/
/* Write sector(s)                                                       */
/*-----------------------------------------------------------------------*/

DRESULT USER_SOFTSPI_write(
    BYTE pdrv,        /* Physical drive number (0) */
    const BYTE *buff, /* Ponter to the data to write */
    DWORD sector,     /* Start sector number (LBA) */
    UINT count        /* Number of sectors to write (1..128) */
)
{
    struct response response;
    const uint8_t start_block_token = START_BLOCK_TOKEN;

    /* pdrv should be 0 */
    if (pdrv || !count)
        return RES_PARERR;

    /* no disk */
    if (Stat & STA_NOINIT)
        return RES_NOTRDY;

    /* write protection */
    if (Stat & STA_PROTECT)
        return RES_WRPRT;

    /* convert to byte address */
    if (!(CardType & CT_BLOCK))
        sector *= 512;

    SELECT();

    switch_ospi_gpio(false);

    if (count == 1)
    {
        /* WRITE_SINGLE_BLOCK */
        do
        {
            response = send_cmd(WRITE_SINGLE_BLOCK, sector);
        } while (response.r0);

        // Send dummy pre-send byte and start block token
        SoftSpi_WriteDummyRead(sd.spi, NULL, 1);
        SoftSpi_WriteRead(sd.spi, &start_block_token, NULL, 1);

        SoftSpi_WriteRead(sd.spi, buff, NULL, BLOCK_SIZE);

        if (finish_write_cmd()) {
            count = 0;
        }
    }
    else
    {
        do
        {
            do
            {
                response = send_cmd(WRITE_SINGLE_BLOCK, sector);
            } while (response.r0);

            // Send dummy pre-send byte and start block token
            SoftSpi_WriteDummyRead(sd.spi, NULL, 1);
            SoftSpi_WriteRead(sd.spi, &start_block_token, NULL, 1);

            SoftSpi_WriteRead(sd.spi, buff, NULL, BLOCK_SIZE);

            if(!finish_write_cmd()) {
                break;
            }

            buff += BLOCK_SIZE;
            if (!(CardType & CT_BLOCK))
            {
                sector += 512;
            }
            else
            {
                sector++;
            }

        } while (--count);
    }

    /* Idle */
    DESELECT();
    SD_ReadyWait();
    switch_ospi_gpio(true);

    return count ? RES_ERROR : RES_OK;
}

/*-----------------------------------------------------------------------*/
/* Miscellaneous drive controls other than data read/write               */
/*-----------------------------------------------------------------------*/

DRESULT USER_SOFTSPI_ioctl(
    BYTE drv,  /* Physical drive number (0) */
    BYTE ctrl, /* Control command code */
    void *buff /* Pointer to the conrtol data */
)
{
    DRESULT res;
    uint8_t *ptr = buff;
    //    WORD csize;

    /* pdrv should be 0 */
    if (drv)
        return RES_PARERR;
    res = RES_ERROR;

    if (ctrl == CTRL_POWER)
    {
        switch (*ptr)
        {
        case 0:
            SD_PowerOff(); /* Power Off */
            res = RES_OK;
            break;
        case 1:
            SD_PowerOn(); /* Power On */
            res = RES_OK;
            break;
        case 2:
            *(ptr + 1) = SD_CheckPower();
            res = RES_OK; /* Power Check */
            break;
        default:
            res = RES_PARERR;
        }
    }
    else
    {
        /* no disk */
        if (Stat & STA_NOINIT)
        {
            return RES_NOTRDY;
        }
        SELECT();
        switch_ospi_gpio(false);

        switch (ctrl)
        {
        case CTRL_SYNC:
            if (SD_ReadyWait() == 0xFF)
                res = RES_OK;
            break;
        default:
            res = RES_ERROR;
            break;
        }
        switch_ospi_gpio(true);
    }
    return res;
}
