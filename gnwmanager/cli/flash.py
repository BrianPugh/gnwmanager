from collections import namedtuple
from datetime import datetime
from pathlib import Path

import typer
from tqdm import tqdm
from typer import Argument, Option
from typing_extensions import Annotated

from gnwmanager.cli._parsers import int_parser
from gnwmanager.utils import sha256
from gnwmanager.validation import validate_extflash_offset

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    add_completion=False,
    help="Flash firmware to device.",
)


def _chunk_bytes(data, chunk_size):
    return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]


def _pad_bytes(data):
    pad_size = (8192 - len(data) % 8192) % 8192
    if pad_size == 0:
        return data
    return data + (b"\xFF" * pad_size)


@app.command()
def ext(
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
            help="Offset into external flash.",
        ),
    ] = 0,
):
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


@app.command()
def bank1(
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
            max=256 << 10,
            parser=int_parser,
            help="Offset into bank.",
        ),
    ] = 0,
):
    """Flash to internal flash bank 1."""
    from .main import gnw

    data = _pad_bytes(file.read_bytes())
    gnw.program(1, offset, data)


@app.command()
def bank2(
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
            max=256 << 10,
            parser=int_parser,
            help="Offset into bank.",
        ),
    ] = 0,
):
    """Flash to internal flash bank 2."""
    from .main import gnw

    data = _pad_bytes(file.read_bytes())
    gnw.program(2, offset, data)
