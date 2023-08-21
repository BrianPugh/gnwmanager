from pathlib import Path
from typing import Optional

from elftools.elf.elffile import ELFFile
from intervaltree import Interval, IntervalTree
from tqdm import tqdm
from typer import Option
from typing_extensions import Annotated

from gnwmanager.utils import find_elf


def create_func_lookup(elf: Path) -> IntervalTree:
    tree = IntervalTree()
    with elf.open("rb") as f:
        elffile = ELFFile(f)

        symtab = elffile.get_section_by_name(".symtab")
        for symbol in symtab.iter_symbols():
            if "FUNC" in symbol.entry.st_info.type and symbol.entry.st_size:
                start = symbol.entry.st_value
                end = start + symbol.entry.st_size
                tree[start:end] = symbol

    return tree


def profiler(
    elf: Annotated[
        Optional[Path],
        Option(
            help='Project\'s ELF file. Defaults to searching "build/" directory.',
        ),
    ] = None,
):
    from .main import session

    target = session.target

    if elf is None:
        elf = find_elf()

    lookup = create_func_lookup(elf)

    pbar = tqdm(desc="Sampling", unit="iter", unit_scale=True)

    while True:
        target.halt()
        pc = target.read_core_register("pc")
        target.resume()
        pbar.update(1)

    list(lookup[pc])[0].data
