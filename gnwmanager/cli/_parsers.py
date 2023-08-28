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


def int_parser(size_str):
    size_str = str(size_str).lower()

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
