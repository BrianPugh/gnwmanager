#include <sys/types.h>
#include <errno.h>
#include <sys/time.h>
#include <unistd.h>
#include "rg_rtc.h"

int _gettimeofday(struct timeval *tv, void *tzvp)
{
    if (tv)
    {
        // get epoch UNIX time from RTC
        time_t unixTime = GW_GetUnixTime();
        tv->tv_sec = unixTime;
        tv->tv_usec = 0;
        return 0;
    }

    errno = EINVAL;
    return -1;
}