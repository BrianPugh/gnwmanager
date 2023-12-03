from cyclopts import Parameter, validators
from typing_extensions import Annotated

from gnwmanager.gnw import GnW

# Dictionary mapping suffixes to their size in bytes
_suffix_map = {
    # bytes
    "kb": 1024,
    "mb": 1024**2,
    "gb": 1024**3,
    "tb": 1024**4,
    "pb": 1024**5,
    # frequency
    "khz": 1_000,
    "mhz": 1_000_000,
}


def int_parser(type_, *tokens: str):
    size_str = str(tokens[0]).lower()

    # Check if the string starts with '0x', which indicates a hexadecimal number
    if size_str.startswith("0x"):
        base = 16
        size_str = size_str[2:]
    else:
        base = 10

    # Separate the size number and suffix
    for suffix, multiplier in _suffix_map.items():
        if size_str.endswith(suffix):
            num_part = size_str[: -len(suffix)]
            return int(num_part, base) * multiplier

    # Handle base units; remove base suffix
    if size_str.endswith("b"):
        size_str = size_str[:-1]
    if size_str.endswith("hz"):
        size_str = size_str[:-2]

    # If no suffix, assume it's in bytes
    return int(size_str, base)


OffsetType = Annotated[int, Parameter(validator=validators.Number(gte=0), converter=int_parser)]
GnWType = Annotated[GnW, Parameter(parse=False)]


def convert_location(type_, *values) -> int:
    location = values[0]

    if location == "bank1":
        return 0x0800_0000
    elif location == "bank2":
        return 0x0810_0000
    elif location == "ext":
        return 0x9000_0000
    else:
        return int_parser(type_, *values)


def validate_flash_range(type_, value):
    if (0x0800_0000 <= value <= 0x0804_0000) or (0x0810_0000 <= value <= 0x0814_0000) or (value >= 0x9000_0000):
        return
    raise ValueError(f"Invalid flash address 0x{value:08X}.")
