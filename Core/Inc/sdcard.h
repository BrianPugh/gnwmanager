#include <stdint.h>

void sdcard_init_spi1();
void sdcard_deinit_spi1();
void sdcard_init_ospi1();
void sdcard_deinit_ospi1();

void switch_ospi_gpio(uint8_t ToOspi);
