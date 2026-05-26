#ifndef _GW_RTC_H_
#define _GW_RTC_H_

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32h7xx_hal.h"
#include <time.h>

extern RTC_TimeTypeDef GW_currentTime;
extern RTC_DateTypeDef GW_currentDate;

time_t GW_GetUnixTime(void);
void GW_SetUnixTime(uint32_t time);

#ifdef __cplusplus
}
#endif

#endif
