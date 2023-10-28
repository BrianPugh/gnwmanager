# Flashing Firmware
GnWManager can efficiently flash compiled binaries to the following locations:

1. Internal Flash Bank 1 (`bank1`)

2. Internal Flash Bank 2 (`bank2`)

3. External SPI Flash (`ext`)

4. An exact virtual memory address (e.g. `0x08000000` for bank 1)

When flashing data, GnWManager will only flash chunks of data that have changed,
speeding up the process and reducing flash wear.

## Flash Example
The following command will flash a hypothetical binary located at `build/gw_retro_go_intflash.bin` to the first internal bank.

```bash
gnwmanager flash bank1 build/gw_retro_go_intflash.bin
```


Commonly external binary payloads may be flashed at an offset (for example, if dual booting with patched firmware).

```bash
gnwmanager flash ext build/gw_retro_go_extflash.bin --offset=1MB
```

Offsets in gnwmanager can be specified as plain integer bytes (`1048576`), as plain hex (`0x100000`), or as a decimal with units (`1MB`).

The following commands are all equivalent:

```bash
gnwmanager flash ext build/gw_retro_go_extflash.bin --offset=1048576
gnwmanager flash ext build/gw_retro_go_extflash.bin --offset=0x100000
gnwmanager flash ext build/gw_retro_go_extflash.bin --offset=1MB
gnwmanager flash 0x90000000 build/gw_retro_go_extflash.bin --offset=1MB
gnwmanager flash 0x90100000 build/gw_retro_go_extflash.bin
```


## Command Chaining
Frequently, we will want to flash multiple binary payloads to different sections.
Commands can be chained in a single GnWManager session, delimited by `--`.
Each command is interpreted independently.

The following command is also separated on multiple lines for readability.

```bash
gnwmanager \
    flash bank1 build/gw_retro_go_intflash.bin \
    -- flash ext build/gw_retro_go_extflash.bin \
    -- start bank1
```
