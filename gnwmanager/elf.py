from io import BufferedReader
from pathlib import Path

from elftools.elf.elffile import ELFFile
from elftools.elf.sections import Symbol, SymbolTableSection


class SymTab:
    elf: ELFFile
    f: BufferedReader
    symtab: SymbolTableSection

    def __init__(self, path: Path):
        self.path = path

    def __enter__(self):
        self.f = self.path.open("rb")
        self.elf = ELFFile(self.f)

        symtab = self.elf.get_section_by_name(".symtab")

        if symtab is None:
            raise ValueError("No symbol table found.")
        elif not isinstance(symtab, SymbolTableSection):
            raise TypeError(f"Expected a SymbolTableSection symtab, got {type(symtab)}")

        self.symtab = symtab

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.f.close()

    @classmethod
    def find(cls, path=Path("build/")):
        return cls(find_elf(path=path))

    def __getitem__(self, name) -> Symbol:
        syms = self.symtab.get_symbol_by_name(name)
        if syms is None:
            raise ValueError(f'Symbol "{name}" not found')
        return syms[0]


def find_elf(path=Path("build/")) -> Path:
    candidate_elf_files = list(path.glob("*.elf"))
    if not candidate_elf_files:
        raise FileNotFoundError("No ELF files found!")
    if len(candidate_elf_files) > 1:
        raise FileNotFoundError(f"Found {len(candidate_elf_files)} ELF files. Please specify one via --elf.")
    return candidate_elf_files[0]
