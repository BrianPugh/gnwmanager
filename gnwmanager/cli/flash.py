from collections import namedtuple
from datetime import datetime
from pathlib import Path

from tqdm import tqdm
from typer import Argument, Option
from typing_extensions import Annotated

from gnwmanager.cli._parsers import int_parser
from gnwmanager.utils import sha256
from gnwmanager.validation import validate_extflash_offset


def _chunk_bytes(data, chunk_size):
    return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]


def _pad_bytes(data):
    pad_size = (8192 - len(data) % 8192) % 8192
    if pad_size == 0:
        return data
    return data + (b"\xFF" * pad_size)


def flash(
    location: Annotated[
        str,
        Argument(help="Either an absolute flash address (e.g. 0x08000000) or one of {bank1, bank2, ext}"),
    ],
    file: Annotated[
        Path,
        Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            writable=False,
            readable=True,
            resolve_path=True,
            help="Binary file to flash.",
        ),
    ],
    offset: Annotated[
        int,
        Option(
            min=0,
            parser=int_parser,
            help="Offset into flash.",
        ),
    ] = 0,
):
    """Flash firmware to device."""
    from .main import gnw

    data = _pad_bytes(file.read_bytes())

    try:
        addr = int(location, 0)
    except ValueError:
        if location == "bank1":
            gnw.program(1, offset, data)
        elif location == "bank2":
            gnw.program(2, offset, data)
        elif location == "ext":
            _flash_ext(file, offset)
        else:
            raise ValueError(f'Unknown location "{location}"') from None
        return

    if 0x0800_0000 <= addr <= (0x0800_0000 + (256 << 10)):
        gnw.program(1, addr - 0x0800_0000, data)
    elif 0x0810_0000 <= addr <= (0x0810_0000 + (256 << 10)):
        gnw.program(2, addr - 0x0810_0000, data)
    else:
        raise ValueError("Unsupported destination address.")


def _flash_ext(file, offset):
    """Flash to external flash."""
    from .main import gnw

    validate_extflash_offset(offset)

    data = file.read_bytes()
    data_time = file.stat().st_mtime
    data_time = datetime.fromtimestamp(data_time).strftime("%Y-%m-%d %H:%M:%S:%f")

    device_hashes = gnw.read_hashes(offset, len(data))

    chunk_size = gnw.contexts[0]["buffer"].size  # Assumes all contexts have same size buffer
    chunks = _chunk_bytes(data, chunk_size)
    len(chunks)
    [sha256(chunk) for chunk in chunks]

    Packet = namedtuple("Packet", ["addr", "data"])
    packets = [Packet(offset + i * chunk_size, chunk) for i, chunk in enumerate(chunks)]

    # Remove packets where the hash already matches
    packets = [packet for packet, device_hash in zip(packets, device_hashes) if sha256(packet.data) != device_hash]

    for i, packet in enumerate(tqdm(packets)):
        gnw.program(0, packet.addr, packet.data, blocking=False)
        gnw.write_uint32("progress", int(26 * (i + 1) / len(packets)))

    gnw.wait_for_all_contexts_complete()
