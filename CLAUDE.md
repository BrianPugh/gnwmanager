# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GnWManager is a Game & Watch device manager — a Python CLI tool + STM32 firmware that communicates with Game & Watch hardware via debug probes (STLink, JLink, PyOCD, DAPLink, Raspberry Pi). It handles firmware flashing, filesystem management (LittleFS on external flash), device unlocking/locking, screenshots, monitoring, and GDB debugging.

## Development Setup

```bash
poetry install              # Install Python dependencies
pre-commit install          # Install git hooks (ruff, black, codespell, pyright)
```

## Common Commands

```bash
# Python tests
pytest                      # Run all tests
pytest tests/test_foo.py    # Run a single test file
pytest tests/test_foo.py::test_bar  # Run a single test
pytest -x                   # Stop on first failure

# Linting & formatting
ruff check gnwmanager/      # Lint
ruff check --fix gnwmanager/  # Lint with auto-fix
black gnwmanager/ tests/    # Format (line-length=120)

# Build STM32 firmware (requires arm-none-eabi-gcc)
make -j4                    # Produces gnwmanager/firmware.bin and gnwmanager/unlock.bin
make clean                  # Clean build artifacts

# Docs
cd docs && poetry run make html  # Build Sphinx docs
```

## Architecture

### Python Package (`gnwmanager/`)

- **`gnw.py`** — Core `GnW` class: the central abstraction for device communication. Uses memory-mapped variables at fixed addresses for a double-buffered, asynchronous host↔device protocol. Handles LZMA-compressed data transfer, hashing, flash operations via two alternating contexts.

- **`cli/`** — CLI built with [cyclopts](https://github.com/BrianPugh/cyclopts). Entry point: `gnwmanager.cli.main:run_app`. Each command is a separate module (`_flash.py`, `_filesystem.py`, `_unlock.py`, etc.). Custom argument parsers in `_parsers.py`. Device model detection in `devices.py`.

- **`ocdbackend/`** — Debug probe abstraction using the `autoregistry` Registry pattern. `OCDBackend` (in `base.py`) is the abstract base; concrete implementations are `openocd_backend.py` and `pyocd_backend.py`. Backends are discovered automatically via the registry.

- **`filesystem.py`** — LittleFS integration via `littlefs-python`. Custom `LfsDriverContext` provides direct flash read/write through the debug probe.

- **`cli/gnw_patch/`** — Firmware binary patching utilities with device-specific (Mario/Zelda) patch binaries. Excluded from linting.

### STM32 Firmware (`Core/`, `Drivers/`)

C firmware for STM32H7B0 (Cortex-M7) that runs from RAM on the Game & Watch device. Compiled with `arm-none-eabi-gcc` via the Makefile. Key source in `Core/Src/` includes `gnwmanager.c` (main protocol handler), flash drivers, LCD, SD card, LZMA decompression, and FatFs.

`Drivers/` contains STM32 HAL drivers (third-party, excluded from linting).

### Communication Protocol

The host Python code and on-device firmware communicate through memory-mapped variables at fixed SRAM addresses (starting at `0x2400_0000`). The protocol uses two contexts (double-buffering) for overlapping data transfer and flash operations. Key variables include status, progress, hash digests, and 256KB data buffers per context.

## Code Style

- **Line length:** 120 (black + ruff)
- **Docstrings:** numpy-style napoleon
- **Paths:** Always use `pathlib.Path`, never `os.path`
- **Errors:** Raise exceptions, never return sentinel values
- **Strings:** Use f-strings
- **Python target:** 3.9+
- **Linter:** ruff with rules: B, C4, D, E, F, I, ISC, N, PGH, PTH, Q, SIM, TRY, UP, W, YTT
- **Type checker:** pyright
