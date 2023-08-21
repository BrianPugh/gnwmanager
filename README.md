<div align="center">
  <img src="https://github.com/BrianPugh/gnwmanager/blob/main/assets/screenshot.png">
</div>

<div align="center">

![Python compat](https://img.shields.io/badge/>=python-3.8-blue.svg)
![PyPi](https://img.shields.io/pypi/v/gnwmanager.svg)

</div>

# GNWManager

GNWManager is THE game-and-watch device manager. GNWManager is responsible for getting firmware
onto your device, managing the filesystem, and other device administrative tasks.

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
Currently, GNWManager is not available on PyPI (but the name is reserved) until upstream PRs are merged.
Until then, the best way to install GNWManager is:

```bash
git clone https://github.com/BrianPugh/gnwmanager.git
cd gnwmanager
pipx install .
```

That's it!

## Usage
To see available commands, run `gnwmanager --help`.

```bash
$ gnwmanager --help

 Usage: gnwmanager [OPTIONS] COMMAND [ARGS]...

╭─ Options ──────────────────────────────────────────────────────────────────────────────╮
│ --version  -v        Print gnwmanager version.                                         │
│ --help               Show this message and exit.                                       │
╰────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ─────────────────────────────────────────────────────────────────────────────╮
│ debug             GnWManager internal debugging tools                                  │
│ disable-debug     Disable the microcontroller's debug block.                           │
│ erase             Erase a section of flash.                                            │
│ flash             Flash firmware to device.                                            │
│ format            Format device's filesystem.                                          │
│ gdb               Launch a gdbserver and connect to it with gdb.                       │
│ gdbserver         Launch a gdbserver.                                                  │
│ ls                List contents of device directory.                                   │
│ mkdir             Create a directory on device.                                        │
│ monitor           Monitor the device's stdout logging buffer.                          │
│ mv                Move/Rename a file or directory.                                     │
│ pull              Pull a file or folder from device.                                   │
│ push              Push file(s) and folder(s) to device.                                │
│ screenshot        Capture and transfer screenshots from device.                        │
│ shell             Launch an interactive shell to browse device filesystem.             │
│ start             Start firmware at location.                                          │
╰────────────────────────────────────────────────────────────────────────────────────────╯
```
