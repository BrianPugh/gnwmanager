import hashlib
import lzma
import struct
from enum import Enum
from pathlib import Path

from PIL import Image


class Color(Enum):
    NONE = 0
    BLACK = 90
    RED = 91
    GREEN = 92
    YELLOW = 93
    BLUE = 94
    MAGENTA = 95
    CYAN = 96
    WHITE = 97


def colored(color: Color, text: str) -> str:
    return f"\033[{color.value}m{text}\033[{Color.NONE.value}m"


def sha256(data) -> bytes:
    return hashlib.sha256(data).digest()


EMPTY_HASH_DIGEST = sha256(b"")


def compress_lzma(data) -> bytes:
    compressed_data = lzma.compress(
        data,
        format=lzma.FORMAT_ALONE,
        filters=[
            {
                "id": lzma.FILTER_LZMA1,
                "preset": 6,
                "dict_size": 16 * 1024,
            }
        ],
    )

    return compressed_data[13:]


def convert_framebuffer(data: bytes) -> Image.Image:
    """Convert a raw RGB565 framebuffer into a PIL Image.

    Parameters
    ----------
    data: bytes
        RGB565 data (153600 bytes)
    """
    if len(data) != (320 * 240 * 2):
        raise ValueError

    img = Image.new("RGB", (320, 240))
    pixels = img.load()
    index = 0
    for y in range(240):
        for x in range(320):
            (color,) = struct.unpack("<H", data[index : index + 2])
            red = int(((color & 0b1111100000000000) >> 11) / 31.0 * 255.0)
            green = int(((color & 0b0000011111100000) >> 5) / 63.0 * 255.0)
            blue = int((color & 0b0000000000011111) / 31.0 * 255.0)
            pixels[x, y] = (red, green, blue)
            index += 2
    return img


def find_elf(path=Path("build/")) -> Path:
    candidate_elf_files = list(path.glob("*.elf"))
    if not candidate_elf_files:
        raise FileNotFoundError("No ELF files found!")
    if len(candidate_elf_files) > 1:
        raise FileNotFoundError(f"Found {len(candidate_elf_files)} ELF files. Please specify one via --elf.")
    elf = candidate_elf_files[0]
    return elf
