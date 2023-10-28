# Extracting Screenshots

#### Dumping
Pulls and re-encodes a screenshot file from the device.

```bash
$ gnwmanager screenshot dump --help

 Usage: gnwmanager screenshot dump [OPTIONS]

 Decode a saved screenshot from device filesystem.
 GnWManager assumes the file represents a Tamp-compressed 320*240 RGB565 framebuffer.

╭─ Options ──────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --src             PATH        Path to screenshot file. [default: /SCREENSHOT]                                      │
│ --dst             PATH        Destination file or directory [default: screenshot.png]                              │
│ --offset          INT_PARSER  Distance in bytes from the END of the filesystem, to the END of flash. [default: 0]  │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

By default, it will attempt to pull the file `/SCREENSHOT`.
For the on-device screenshot file format, see [Developer Notes](#developer-notes).

#### Capturing
To capture the current active framebuffer of the running system, invoke:

```bash
$ gnwmanager screenshot capture --help

 Usage: gnwmanager screenshot capture [OPTIONS]

 Capture a live screenshot from device's framebuffer.

╭─ Options ─────────────────────────────────────────────────────────────────────────────────╮
│ --dst                  PATH  Destination file or directory [default: screenshot.png]      │
│ --elf                  PATH  Project's ELF file. Defaults to searching "build/" directory.│
│ --framebuffer          TEXT  framebuffer variable name [default: framebuffer]             │
╰───────────────────────────────────────────────────────────────────────────────────────────╯
```

By default, this looks for a variable named `framebuffer` in the project's ELF file.
It then pulls that `320*240` RGB565 array, and re-encodes it to a png or jpg file.

#### Developer Notes
The on-device screenshot format is simply a Tamp-compressed screenshot buffer.
[Tamp](https://github.com/BrianPugh/tamp) is a lossless compression library aimed for microcontroller targets.

Example C code:

```
#include "tamp/compressor.h"

uint16_t framebuffer[320*240];

#define TAMP_WINDOW_BUFFER_BITS 10  // 1KB
static unsigned char tamp_window_buffer[1 << TAMP_WINDOW_BUFFER_BITS];

TampCompressor c;
TampConf conf = {.window=TAMP_WINDOW_BUFFER_BITS, .literal=8, .use_custom_dictionary=false};

// Initialize Tamp compression engine.
assert(TAMP_OK == tamp_compressor_init(&c, &conf, tamp_window_buffer));

// Tamp has a streaming interface, but for this example, we'll
// do a simpler, less-memory-efficient, single-shot compression.
static unsigned char output_buffer[1 << TAMP_WINDOW_BUFFER_BITS];
size_t output_written_size;
tamp_compressor_compress_and_flush(
     &compressor,
     framebuffer, sizeof(framebuffer), NULL,
     output_buffer, sizeof(output_buffer), &output_written_size
);

// Compressed screenshot data is now in output_buffer
printf("Compressed size: %d\n", output_written_size);
```
