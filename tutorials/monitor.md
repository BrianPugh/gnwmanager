# Stdout Monitoring
Printing to `stdout` is a common debugging technique to gain insight on the state of your program.
Unfortunately, due to the game & watch's hardware configuration, we don't have an independent communication channel for `stdout`.
We can get around this by rerouting `stdout` to a circular buffer on-device, and monitoring this region of memory for changes.

In your program's `main.c`, you will need code like:

```c
char logbuf[1024 * 4]  __attribute__((aligned(4)));
volatile uint32_t log_idx;

int _write(int file, char *ptr, int len)
{
  uint32_t idx = log_idx;
  if (idx + len + 1 > sizeof(logbuf)) {
    idx = 0;
  }

  memcpy(&logbuf[idx], ptr, len);
  idx += len;
  logbuf[idx] = '\0';

  log_idx = idx;

  return len;
}
```

The `game-and-watch-retro-go` repository already has this `_write` hook.

To read and print out this message buffer on your computer, run:

```bash
gnwmanager monitor
```


## Advanced Usage
Run `gnwmanager monitor --help` to view additional options.

```bash
$ gnwmanager monitor --help

 Usage: gnwmanager monitor [OPTIONS]

 Monitor the device's stdout logging buffer.

╭─ Options ────────────────────────────────────────────────────────────────────────────╮
│ --elf             PATH  Project's ELF file. Defaults to searching "build/" directory.│
│ --buffer          TEXT  Log buffer variable name. [default: logbuf]                  │
│ --index           TEXT  Log buffer index variable name. [default: log_idx]           │
│ --help    -h            Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────────────╯
```

`gnwmanager monitor` works by reading your projects ELF file, and searches for the defined variables `logbuf` and `log_idx`.
By default, GnWManager will search for and use the single ELF file in the `build/` directory.
If multiple ELF files are found, an explicit ELF file will need to be specified.
The `logbuf` and `log_idx` variable names can also be configured via `--buffer` and `--index`, respectively.
