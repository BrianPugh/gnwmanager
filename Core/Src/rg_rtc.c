#include "main.h"
#include "rg_rtc.h"
#include "stm32h7xx_hal.h"


RTC_TimeTypeDef GW_currentTime = {0};
RTC_DateTypeDef GW_currentDate = {0};

// Howard Hinnant's days_from_civil / civil_from_days. UTC only, no DST/tz —
// replaces newlib mktime/gmtime which otherwise drag in ~2.4KB of tz code.
static int32_t days_from_civil(int y, unsigned m, unsigned d) {
    y -= m <= 2;
    const int era = y / 400;
    const unsigned yoe = (unsigned)(y - era * 400);
    const unsigned doy = (153u * (m > 2 ? m - 3u : m + 9u) + 2u) / 5u + d - 1u;
    const unsigned doe = yoe * 365u + yoe / 4u - yoe / 100u + doy;
    return era * 146097 + (int32_t)doe - 719468;
}

static void civil_from_days(int32_t z, int *y, unsigned *m, unsigned *d) {
    z += 719468;
    const int era = (z >= 0 ? z : z - 146096) / 146097;
    const unsigned doe = (unsigned)(z - era * 146097);
    const unsigned yoe = (doe - doe / 1460u + doe / 36524u - doe / 146096u) / 365u;
    const unsigned doy = doe - (365u * yoe + yoe / 4u - yoe / 100u);
    const unsigned mp = (5u * doy + 2u) / 153u;
    *d = doy - (153u * mp + 2u) / 5u + 1u;
    *m = mp < 10u ? mp + 3u : mp - 9u;
    *y = (int)yoe + era * 400 + (*m <= 2);
}

time_t GW_GetUnixTime(void) {
    HAL_RTC_GetTime(&hrtc, &GW_currentTime, RTC_FORMAT_BIN);
    HAL_RTC_GetDate(&hrtc, &GW_currentDate, RTC_FORMAT_BIN);

    int32_t days = days_from_civil(2000 + GW_currentDate.Year,
                                   GW_currentDate.Month,
                                   GW_currentDate.Date);
    return (time_t)days * 86400
         + (time_t)GW_currentTime.Hours * 3600
         + (time_t)GW_currentTime.Minutes * 60
         + (time_t)GW_currentTime.Seconds;
}

void GW_SetUnixTime(uint32_t time) {
    int32_t days = (int32_t)(time / 86400u);
    uint32_t tod = time % 86400u;
    int year;
    unsigned month, day;
    civil_from_days(days, &year, &month, &day);

    // RTC weekday: 1=Mon..7=Sun. 1970-01-01 is a Thursday (days=0 -> 4).
    GW_currentDate.WeekDay = (uint8_t)(((unsigned)(days + 3) % 7u) + 1u);
    GW_currentDate.Year    = (uint8_t)(year - 2000);
    GW_currentDate.Month   = (uint8_t)month;
    GW_currentDate.Date    = (uint8_t)day;

    GW_currentTime.Hours   = (uint8_t)(tod / 3600u);
    GW_currentTime.Minutes = (uint8_t)((tod / 60u) % 60u);
    GW_currentTime.Seconds = (uint8_t)(tod % 60u);

    if (HAL_RTC_SetTime(&hrtc, &GW_currentTime, RTC_FORMAT_BIN) != HAL_OK ||
        HAL_RTC_SetDate(&hrtc, &GW_currentDate, RTC_FORMAT_BIN) != HAL_OK)
    {
        Error_Handler();
    }
}
