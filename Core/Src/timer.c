#include "timer.h"
#include "main.h"

static uint32_t timerTickStart[2],timerTickDelay[2]; /* 1ms Timer Counters */

void timer_on(uint8_t timer_index,uint32_t waitTicks) {
    timerTickStart[timer_index] = HAL_GetTick();
    timerTickDelay[timer_index] = waitTicks;
}

uint8_t timer_status(uint8_t timer_index) {
    wdog_refresh();
    return ((HAL_GetTick() - timerTickStart[timer_index]) < timerTickDelay[timer_index]);
}
