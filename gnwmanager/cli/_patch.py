"""``flash-patch``: patch the stock firmware with game-and-watch-patch and flash it.

The patcher is the ``gnwmanager/gnw_patch`` submodule (only its ``patches/`` and
``tools/re/*.syms`` go into the wheel). Its compiled code comes prebuilt, one ELF per
C-build configuration, packed in ``gnwmanager/patch_elfs.tar.xz`` (``make patch-elfs``),
so users need no compiler. Neither holds any Nintendo firmware bytes.
"""

import hashlib
import importlib.resources
import logging
import tarfile
import tempfile
from pathlib import Path
from typing import Annotated, Any, Callable, Sequence

from cyclopts import Parameter

from gnwmanager.cli._bootloader import get_bootloader
from gnwmanager.cli.main import app
from gnwmanager.gnw import GnW

log = logging.getLogger(__name__)

MODELS = ("mario", "zelda")
# Options that name our compiled code; any of them replaces the prebuilt ELFs.
CODE_OPTIONS = ("--prebuilt", "--elf", "--patch")
# The prebuilt ELFs, in the package.
PATCH_ELFS = "patch_elfs.tar.xz"
# gnwmanager's --help shows flash-patch's own help, so the patcher's is this.
PATCHER_HELP = "--patcher-help"
# --sd-bootloader builds dual-boot Sylverb's SD bootloader here.
SD_BOOTLOADER = 0x0803_2000


class PatchError(Exception):
    pass


def _option(argv: Sequence[str], name: str) -> bool:
    return any(a == name or a.startswith(name + "=") for a in argv)


def _sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def detect_device(backup_dir: Path) -> str:
    """The model whose stock internal backup is in ``backup_dir``.

    Raises
    ------
    PatchError
        No backup, or backups of both models (the choice is then the user's: mario, zelda or amalgam).
    """
    from gnwmanager.gnw_patch.patches import Device

    found, wrong = [], []
    for model in MODELS:
        path = backup_dir / f"internal_flash_backup_{model}.bin"
        if not path.exists():
            continue
        if _sha1(path) == Device.registry[model].Int.STOCK_ROM_SHA1_HASH:
            found.append(model)
        else:
            wrong.append(path)
    if len(found) == 1:
        return found[0]
    if found:
        raise PatchError(f"Found stock backups of both models in {backup_dir}; pass --device=mario|zelda|amalgam.")
    if wrong:
        bad = ", ".join(str(p) for p in wrong)
        raise PatchError(f"{bad}: not a stock backup (dump it from an unpatched unit with gnwmanager dump).")
    names = " or ".join(f"internal_flash_backup_{m}.bin" for m in MODELS)
    raise PatchError(f"No {names} in {backup_dir}; pass --backup-dir, or dump them with gnwmanager dump.")


def patch_argv(argv: Sequence[str], work_dir: Path) -> list[str]:
    """The patcher's command line: ``argv`` plus the defaults gnwmanager supplies.

    The device (from the backups, unless given), and the prebuilt ELFs (``unpack_elfs()``'s),
    output and debug files in ``work_dir`` (unless given).
    """
    from gnwmanager.gnw_patch.patches import options

    argv = ["--help" if a == PATCHER_HELP else a for a in argv]
    if "--help" in argv:
        return argv
    if not _option(argv, "--device"):
        args, _ = options.build_parser().parse_known_args(argv)
        argv.insert(0, f"--device={detect_device(args.backup_dir)}")
    if not any(_option(argv, o) for o in CODE_OPTIONS):
        argv.append(f"--prebuilt={work_dir / 'patch_elfs'}")
    defaults = {
        "--int-output": work_dir / "internal_flash_patched.bin",
        "--ext-output": work_dir / "external_flash_patched.bin",
        "--dump-dir": work_dir / "debug",
    }
    for name, path in defaults.items():
        if not _option(argv, name):
            argv.append(f"{name}={path}")
    return argv


def unpack_elfs(dst: Path):
    """Unpack the prebuilt ELFs into ``dst``."""
    archive = importlib.resources.files("gnwmanager") / PATCH_ELFS
    try:
        f = archive.open("rb")
    except FileNotFoundError:
        raise PatchError(f"No {PATCH_ELFS} in the package; build it with make patch-elfs.") from None
    with f, tarfile.open(fileobj=f, mode="r:xz") as tar:
        # The data filter only exists from python 3.9.17 on.
        kwargs: dict[str, Any] = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
        tar.extractall(dst, **kwargs)


@app.command(name="flash-patch")
def flash_patch(
    *argv: Annotated[str, Parameter(allow_leading_hyphen=True)],
    backend_factory: Annotated[Callable[[], dict[str, Any]], Parameter(parse=False)],
):
    """Patch the stock firmware for dual-boot (game-and-watch-patch) and flash it.

    Every option goes to the patcher; ``gnwmanager flash-patch --patcher-help`` lists them
    (``--device=zelda --patcher-help`` for Zelda's). It reads the stock backups from
    ``--backup-dir`` (default: the current directory): ``internal_flash_backup_<model>.bin``
    and ``flash_backup_<model>.bin``. ``--device`` defaults to the model of the backup found
    there; ``--device=amalgam`` puts both models in one image and needs all 4 backups.
    ``--sd-bootloader`` also flashes the latest release of Sylverb's SD bootloader.
    The unit is connected only after patching succeeds.

    Example::

        gnwmanager flash-patch --sd-bootloader -- start bank1

    https://github.com/BrianPugh/game-and-watch-patch
    """
    from gnwmanager.gnw_patch.patches import cli, options

    with tempfile.TemporaryDirectory() as tmp:
        try:
            argv_full = patch_argv(argv, Path(tmp))
            if not any(_option(argv, o) for o in CODE_OPTIONS):
                unpack_elfs(Path(tmp) / "patch_elfs")
        except PatchError as e:
            raise SystemExit(str(e)) from None
        cli.main(argv_full)  # Exits on --help or a bad option.

        _, models = options.parse(argv_full)
        args = next(iter(models.values()))
        internal = args.int_output.read_bytes()
        external = args.ext_output.read_bytes()
        bank2_path = args.int_output.with_name(args.int_output.stem + "_bank2.bin")
        bank2 = bank2_path.read_bytes() if bank2_path.exists() else b""
    bootloader = b""
    if args.sd_bootloader:
        # The latest release, as flash-bootloader defaults to.
        bootloader = get_bootloader("sylverb/game-and-watch-bootloader", label="0x08032000").read_bytes()

    opts = backend_factory()
    gnw = GnW(opts["factory"]())
    gnw.backend.open()
    try:
        if opts["frequency"] is not None:
            gnw.backend.set_frequency(opts["frequency"])
        gnw.start_gnwmanager()
        if external:
            gnw.flash(0, 0, external, progress=True, desc="patched external firmware")
        if bank2:
            gnw.flash(2, 0, bank2, progress=False)
        gnw.flash(1, 0, internal, progress=False)
        if bootloader:
            gnw.flash(1, SD_BOOTLOADER - 0x0800_0000, bootloader, progress=False)
    finally:
        gnw.backend.close()
