from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from pyocd.flash.file_programmer import FileProgrammer
from tqdm import tqdm
from typer import Argument, Option
from typing_extensions import Annotated

from gnwmanager.cli._start_gnwmanager import start_gnwmanager
from gnwmanager.target import contexts
from gnwmanager.validation import validate_extflash_offset

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False, add_completion=False)


def _chunk_bytes(data, chunk_size):
    return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]


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
            help="Offset into external flash.",
        ),
    ] = 0,
    progress_file: Annotated[
        Optional[Path],
        Argument(
            file_okay=True,
            dir_okay=False,
            writable=True,
            resolve_path=True,
            help="Save/Load progress from a file; allows resuming a interrupted extflash operation.",
        ),
    ] = None,
):
    from .main import session

    validate_extflash_offset(offset)
    start_gnwmanager()

    target = session.target

    data = file.read_bytes()
    data_time = file.stat().st_mtime
    data_time = datetime.fromtimestamp(data_time).strftime("%Y-%m-%d %H:%M:%S:%f")

    chunk_size = contexts[0]["buffer"].size  # Assumes all contexts have same size buffer
    chunks = _chunk_bytes(data, chunk_size)
    total_n_chunks = len(chunks)

    previous_chunks_already_flashed = 0
    # Attempt to resume a previous session.
    if progress_file and progress_file.exists():
        progress_file_time, progress_file_chunks_already_flashed = progress_file.read_text().split("\n")
        progress_file_chunks_already_flashed = int(progress_file_chunks_already_flashed)
        if progress_file_time == data_time:
            previous_chunks_already_flashed = progress_file_chunks_already_flashed
            print(f"Resuming previous session at {previous_chunks_already_flashed}/{total_n_chunks}")

    # https://github.com/tqdm/tqdm/issues/1264
    chunks = chunks[previous_chunks_already_flashed:]

    target.write_int("program_chunk_count", total_n_chunks)

    base_address = offset + (previous_chunks_already_flashed * chunk_size)
    with tqdm(initial=previous_chunks_already_flashed, total=total_n_chunks) as pbar:
        for i, chunk in enumerate(chunks):
            chunk_1_idx = previous_chunks_already_flashed + i + 1
            pbar.update(1)
            target.write_int("program_chunk_idx", chunk_1_idx)
            target.write_ext(base_address + (i * chunk_size), chunk, blocking=False)

            # Save current progress to a file in case progress is interrupted.
            if progress_file:
                # Up to 3 chunks may have been sent to device that may have NOT been written to disk.
                # This is the most conservative estimate of what has been written to disk.
                chunks_already_flashed = max(previous_chunks_already_flashed, chunk_1_idx - 3)
                progress_file.parent.mkdir(exist_ok=True, parents=True)
                progress_file.write_text(f"{data_time}\n{chunks_already_flashed}")

        target.wait_for_all_contexts_complete()
        target.wait_for_idle()

    if progress_file and progress_file.exists():
        progress_file.unlink()


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
            help="Offset into bank.",
        ),
    ] = 0,
):
    from .main import session

    programmer = FileProgrammer(session, progress=None, no_reset=False)
    programmer.program(str(file), base_address=0x0800_0000 + offset)


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
            help="Offset into bank.",
        ),
    ] = 0,
):
    from .main import session

    programmer = FileProgrammer(session, progress=None, no_reset=False)
    programmer.program(str(file), base_address=0x0810_0000 + offset)
