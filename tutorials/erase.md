# Flash Erasing
Frequently, you may want to erase some of the device's flash, to confirm things are working as expected.

```bash
$ gnwmanager erase --help

 Usage: gnwmanager erase [OPTIONS] LOCATION:{bank1|bank2|ext|all}

 Erase a section of flash.

╭─ Arguments ───────────────────────────────────────────────────────────────────────╮
│ *    location      LOCATION:{bank1|bank2|ext|all}  Section to erase. [required]   │
╰───────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ─────────────────────────────────────────────────────────────────────────╮
│ --help  -h        Show this message and exit.                                     │
╰───────────────────────────────────────────────────────────────────────────────────╯
```

For example, to only erase `bank1`, run:

```bash
gnwmanager erase bank1
```
