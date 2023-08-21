from pathlib import Path
from time import time
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
    # samples_per_second: Annotated[
    #    float,
    #    Option(
    #        help="Target number of samples per second."
    #    )
    # ] = 100,
    sample_duration: Annotated[float, Option(help="Sampling duration in seconds.")] = 30,
):
    from .main import session

    target = session.target

    if elf is None:
        elf = find_elf()

    lookup = create_func_lookup(elf)

    pbar = tqdm(desc="Sampling", unit="iter", unit_scale=True)

    pcs = []
    t_start = time()
    while True:
        target.halt()
        pcs.append(target.read_core_register("pc"))
        target.resume()
        pbar.update(1)

        # Rate limiting and exiting
        t_current = time()
        if t_current - t_start >= sample_duration:
            break

    counter = {}
    for pc in pcs:
        try:
            sym = list(lookup[pc])[0].data
        except IndexError:
            counter["<<UNKNOWN_PC>>"] = counter.get("<<UNKNOWN_PC>>", 0) + 1
            continue
        counter[sym.name] = counter.get(sym.name, 0) + 1

    sorted_counter = dict(sorted(counter.items(), key=lambda item: item[1]))

    for key, value in sorted_counter.items():
        percentage = 100 * (value / len(pcs))
        print(f"{key}: {percentage:.1f}%")
