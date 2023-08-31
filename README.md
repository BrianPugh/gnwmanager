<div align="center">
  <img src="https://github.com/BrianPugh/gnwmanager/blob/main/assets/screenshot.png">
</div>

<div align="center">

![Python compat](https://img.shields.io/badge/>=python-3.8-blue.svg)
![PyPi](https://img.shields.io/pypi/v/gnwmanager.svg)

</div>

# GnWManager

GnWManager is THE game-and-watch device manager. GnWManager is a command line tool
who's responsible for getting firmware onto your device, managing the filesystem,
and other device administrative tasks.

GnWManager accomplishes this via a small bundled pre-compiled firmware that gets
executed from the STM32's RAM.

## Features

* Standalone and simple to install.
    * No more installing many different tools with various patches!
* Fast internal and external flash firmware flashing.
    * Hardware-accelerated hashing for rapid duplicate discovery.
        * Only syncs changed data.
        * Minimizes flash erases and writes, extending flash lifespan.
    * Double buffered, asynchronous, LZMA-compressed transfers for maximum speed.
* Complete filesystem management.
    * Backup and restore files.
    * Interactive filesystem explorer.
* Automatic Real-Time-Clock (RTC) configuration.
* Developer tools:
    * Easily monitor device ``printf`` statements and launch GDB sessions.
    * Capture screenshots, regardless of the running firmware.

## Installation

It is **highly** recommended to use [pipx](https://pypa.github.io/pipx/installation/) to install GnWManager.
Currently, GnWManager is not available on PyPI (but the name is reserved) until upstream PRs are merged.
Until then, the best way to install GnWManager is:

```bash
git clone https://github.com/BrianPugh/gnwmanager.git
cd gnwmanager
pipx install .
```

That's it!

## Compatibility
GnWManager works with all major operating systems: Windows, Mac, and Linux.
GnWManager is also compatible with the following probes:

1. [Raspberry Pi Pico](https://www.raspberrypi.com/products/raspberry-pi-pico/) (Recommended)
2. [STLink](https://www.st.com/en/development-tools/st-link-v2.html)
3. [JLink](https://www.segger.com/products/debug-probes/j-link/#models)
4. [DAPLink](https://daplink.io) (~10x slower than other probes)

Unfortunately, GnWManager **is not** compatible with raspberry pi gpio.
There is currently an effort to add support in [pyocd](https://github.com/pyocd/pyOCD), the underlying library that GnWManager uses for hardware interactions.


#### STLink
Hook up your STLink to your game and watch as follows:

<div align="center">
  <img width=512 src="https://github.com/BrianPugh/gnwmanager/blob/main/assets/stlinkv2.png">
</div>


#### Raspberry Pi Pico

All Raspberry Pi Picos can be transformed into programmers via the [picoprobe project](https://github.com/raspberrypi/picoprobe).

1. Download `picoprobe.uf2` from [picoprobe releases](https://github.com/raspberrypi/picoprobe/releases).
2. Hold BOOT button on the  pico and plug it into the computer. It should show up as a USB drive. Drag and drop `picoprobe.uf2` to it.
3. Hook up the 3 wires (GND, GP2, GP3) to (GND, SDCLK, SWDIO), respectively.

<div align="center">
  <img width=512 src="https://github.com/BrianPugh/gnwmanager/blob/main/assets/pi-pico.png">
</div>


## Usage
To see available commands, run `gnwmanager --help`.

```console
$ gnwmanager --help

 Usage: gnwmanager [OPTIONS] COMMAND [ARGS]...

 Game And Watch Device Manager.
 Manages device flashing, filesystem management, peripheral configuration, and more.

╭─ Options ──────────────────────────────────────────────────────────────────────────╮
│ --version    -v                  Print gnwmanager version.                         │
│ --frequency  -f      INT_PARSER  Probe frequency. [default: None]                  │
│ --backend    -b      [pyocd]     OCD Backend. [default: pyocd]                     │
│ --help                           Show this message and exit.                       │
╰────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ─────────────────────────────────────────────────────────────────────────╮
│ debug             GnWManager internal debugging tools                              │
│ disable-debug     Disable the microcontroller's debug block.                       │
│ erase             Erase a section of flash.                                        │
│ flash             Flash firmware to device.                                        │
│ format            Format device's filesystem.                                      │
│ gdb               Launch a gdbserver and connect to it with gdb.                   │
│ gdbserver         Launch a gdbserver.                                              │
│ ls                List contents of device directory.                               │
│ mkdir             Create a directory on device.                                    │
│ monitor           Monitor the device's stdout logging buffer.                      │
│ mv                Move/Rename a file or directory.                                 │
│ pull              Pull a file or folder from device.                               │
│ push              Push file(s) and folder(s) to device.                            │
│ screenshot        Capture and transfer screenshots from device.                    │
│ shell             Launch an interactive shell to browse device filesystem.         │
│ start             Start firmware at location.                                      │
│ tree              List contents of device directory and its descendants.           │
╰────────────────────────────────────────────────────────────────────────────────────╯
```
