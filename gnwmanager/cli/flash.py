from collections import namedtuple
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from tqdm import tqdm
from typer import Argument, Option
from typing_extensions import Annotated

from gnwmanager.cli._parsers import int_parser
from gnwmanager.target import contexts
from gnwmanager.utils import sha256
from gnwmanager.validation import validate_extflash_offset

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False, add_completion=False)


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
    from .main import session

    target = session.target

    validate_extflash_offset(offset)

    data = file.read_bytes()
    data_time = file.stat().st_mtime
    data_time = datetime.fromtimestamp(data_time).strftime("%Y-%m-%d %H:%M:%S:%f")

    device_hashes = target.read_hashes(offset, len(data))

    chunk_size = contexts[0]["buffer"].size  # Assumes all contexts have same size buffer
    chunks = _chunk_bytes(data, chunk_size)
    len(chunks)
    [sha256(chunk) for chunk in chunks]

    Packet = namedtuple("Packet", ["addr", "data"])
    packets = [Packet(offset + i * chunk_size, chunk) for i, chunk in enumerate(chunks)]

    # Remove packets where the hash already matches
    packets = [packet for packet, device_hash in zip(packets, device_hashes) if sha256(packet.data) != device_hash]

    for i, packet in enumerate(tqdm(packets)):
        target.prog(0, packet.addr, packet.data, blocking=False)
        target.write_int("progress", int(26 * (i + 1) / len(packets)))

    target.wait_for_all_contexts_complete()
    target.wait_for_idle()  # Wait for the early-return context to complete.


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
    from .main import session

    target = session.target
    data = _pad_bytes(file.read_bytes())
    target.prog(1, offset, data)


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
    from .main import session

    target = session.target
    data = _pad_bytes(file.read_bytes())
    target.prog(2, offset, data)
