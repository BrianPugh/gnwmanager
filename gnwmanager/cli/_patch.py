"""``flash-patch``: patch the stock firmware with game-and-watch-patch and flash it.

The patcher is the ``gnwmanager/gnw_patch`` submodule (only its ``patches/`` and
``tools/re/*.syms`` go into the wheel). Its compiled code comes prebuilt, one ELF per
C-build configuration, packed in ``gnwmanager/patch_elfs.tar.xz`` (``make patch-elfs``),
so users need no compiler. Neither holds any Nintendo firmware bytes.
"""

import hashlib
import importlib.resources
import logging
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Callable, Optional, Sequence

from cyclopts import Parameter

from gnwmanager.cli._bootloader import get_bootloader
from gnwmanager.cli.main import app
from gnwmanager.gnw import GnW

log = logging.getLogger(__name__)

MODELS = ("mario", "zelda")
DEVICES = (*MODELS, "amalgam")
BOOTLOADER_REPO = "sylverb/game-and-watch-bootloader"
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


def model_of(internal: Path) -> Optional[str]:
    """The model ``internal`` is the stock internal backup of, if any."""
    from gnwmanager.gnw_patch.patches import Device

    digest = _sha1(internal)
    return next((m for m in MODELS if digest == Device.registry[m].Int.STOCK_ROM_SHA1_HASH), None)


def detect_device(backup_dir: Path) -> str:
    """The model whose stock internal backup is in ``backup_dir``.

    Raises
    ------
    PatchError
        No backup, or backups of both models (the choice is then the user's: mario, zelda or amalgam).
    """
    found, wrong = [], []
    for model in MODELS:
        path = backup_dir / f"internal_flash_backup_{model}.bin"
        if not path.exists():
            continue
        if model_of(path) == model:
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


@dataclass
class Command:
    """``flash-patch``'s command line, split into the patcher's and gnwmanager's options."""

    argv: list[str]
    bootloader_repo: str = BOOTLOADER_REPO
    bootloader_tag: str = "latest"


def _pop_value(argv: list[str], name: str) -> Optional[str]:
    """Removes ``name VALUE`` or ``name=VALUE`` from ``argv``; returns VALUE."""
    for i, arg in enumerate(argv):
        if arg == name:
            if i + 1 == len(argv):
                raise PatchError(f"{name} needs a value.")
            value = argv[i + 1]
            del argv[i : i + 2]
            return value
        if arg.startswith(name + "="):
            del argv[i]
            return arg.split("=", 1)[1]
    return None


def _positionals(argv: list[str]) -> list[str]:
    """The tokens of ``argv`` that aren't options or their values (the patcher takes none)."""
    from gnwmanager.gnw_patch.patches import Device, options

    parser = options.build_parser()
    parser.conflict_handler = "resolve"  # The 2 models share some option names.
    for model in MODELS:
        Device.registry[model].add_arguments(parser)
    _, extras = parser.parse_known_args(argv)
    return [a for a in extras if not a.startswith("-")]


def _legacy(argv: list[str], work_dir: Path) -> Command:
    """Translates the old ``flash-patch MODEL INTERNAL EXTERNAL`` form and gnwmanager's own options.

    ``MODEL`` becomes ``--device``, the 2 backups are copied into ``work_dir/backups`` (the
    ``--backup-dir``) under the names the patcher reads, and ``--bootloader`` is
    ``--sd-bootloader``.
    """
    from gnwmanager.gnw_patch.patches import options

    if argv and argv[0] in DEVICES:
        if _option(argv, "--device"):
            raise PatchError(f"Give the model once: {argv[0]} or --device.")
        argv[0] = f"--device={argv[0]}"
    cmd = Command(argv)
    cmd.bootloader_repo = _pop_value(argv, "--bootloader-repo") or cmd.bootloader_repo
    cmd.bootloader_tag = _pop_value(argv, "--bootloader-tag") or cmd.bootloader_tag
    argv[:] = ["--sd-bootloader" if a == "--bootloader" else a for a in argv]
    if "--no-second-beep" in argv:
        argv.remove("--no-second-beep")
        log.warning("--no-second-beep is now a setting in the clock menu; ignoring it.")
    if "--help" in argv:
        return cmd

    paths = _positionals(argv)
    if not paths:
        return cmd
    if len(paths) != 2:
        raise PatchError(f"Expected the 2 stock backups (INTERNAL EXTERNAL), got: {' '.join(paths)}")
    if _option(argv, "--backup-dir"):
        raise PatchError("Give the stock backups as INTERNAL EXTERNAL or with --backup-dir, not both.")
    for path in paths:
        argv.remove(path)
    internal, external = (Path(p) for p in paths)
    for path in (internal, external):
        if not path.is_file():
            raise PatchError(f"{path}: no such file.")
    if _option(argv, "--device"):
        model = options.build_parser().parse_known_args(argv)[0].device
        if model not in MODELS:
            raise PatchError(f"--device={model} reads its backups from --backup-dir.")
    else:
        model = model_of(internal)
        if model is None:
            raise PatchError(f"{internal}: not a stock backup (dump it from an unpatched unit with gnwmanager dump).")
        argv.insert(0, f"--device={model}")
    backups = work_dir / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(internal, backups / f"internal_flash_backup_{model}.bin")
    shutil.copyfile(external, backups / f"flash_backup_{model}.bin")
    argv.append(f"--backup-dir={backups}")
    return cmd


def patch_command(argv: Sequence[str], work_dir: Path) -> Command:
    """The patcher's command line: ``argv`` plus the defaults gnwmanager supplies.

    The old form translated (``_legacy()``), the device (from the backups, unless given), and
    the prebuilt ELFs (``unpack_elfs()``'s), output and debug files in ``work_dir`` (unless
    given).
    """
    from gnwmanager.gnw_patch.patches import options

    argv = ["--help" if a == PATCHER_HELP else a for a in argv]
    cmd = _legacy(argv, work_dir)
    if "--help" in argv:
        return cmd
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
    return cmd


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


@app.command
def flash_patch(
    *argv: Annotated[str, Parameter(allow_leading_hyphen=True)],
    backend_factory: Annotated[Callable[[], dict[str, Any]], Parameter(parse=False)],
):
    """Patch the stock firmware for dual-boot (game-and-watch-patch) and flash it.

    Every option but ``--bootloader-repo``/``--bootloader-tag`` goes to the patcher;
    ``gnwmanager flash-patch --patcher-help`` lists them (``--device=zelda --patcher-help`` for
    Zelda's). It reads the stock backups from ``--backup-dir`` (default: the current
    directory): ``internal_flash_backup_<model>.bin`` and ``flash_backup_<model>.bin``.
    ``--device`` defaults to the model of the backup found there; ``--device=amalgam`` puts
    both models in one image and needs all 4 backups. ``--sd-bootloader`` also flashes
    Sylverb's SD bootloader (the latest release, unless ``--bootloader-tag`` is given).
    The unit is connected only after patching succeeds.

    The older ``flash-patch MODEL INTERNAL EXTERNAL [OPTIONS]`` form still works
    (``--bootloader`` is ``--sd-bootloader``).

    Example::

        gnwmanager flash-patch --sd-bootloader -- start bank1

    https://github.com/BrianPugh/game-and-watch-patch
    """
    from gnwmanager.gnw_patch.patches import cli, options

    with tempfile.TemporaryDirectory() as tmp:
        try:
            cmd = patch_command(argv, Path(tmp))
            if not any(_option(argv, o) for o in CODE_OPTIONS):
                unpack_elfs(Path(tmp) / "patch_elfs")
        except PatchError as e:
            raise SystemExit(str(e)) from None
        cli.main(cmd.argv)  # Exits on --help or a bad option.

        _, models = options.parse(cmd.argv)
        args = next(iter(models.values()))
        internal = args.int_output.read_bytes()
        external = args.ext_output.read_bytes()
        bank2_path = args.int_output.with_name(args.int_output.stem + "_bank2.bin")
        bank2 = bank2_path.read_bytes() if bank2_path.exists() else b""
    bootloader = b""
    if args.sd_bootloader:
        bootloader = get_bootloader(cmd.bootloader_repo, cmd.bootloader_tag, label="0x08032000").read_bytes()

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
