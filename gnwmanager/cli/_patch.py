"""``flash-patch``: patch the stock firmware with game-and-watch-patch and flash it.

The patcher is the ``gnwmanager/gnw_patch`` submodule (only its ``patches/`` and
``tools/re/*.syms`` go into the wheel). Its compiled code comes prebuilt, one ELF per
C-build configuration, packed in ``gnwmanager/patch_elfs.tar.xz`` (``make patch-elfs``),
so users need no compiler. Neither holds any Nintendo firmware bytes.
"""

import argparse
import importlib.resources
import inspect
import logging
import shutil
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Callable, Literal, Optional, Sequence

from cyclopts import App, Group, Parameter

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
# Patcher options gnwmanager supplies: not shown, or shown in the "Advanced" panel.
HIDDEN_OPTIONS = ("--patch", "--elf")
ADVANCED_OPTIONS = ("--prebuilt", "--int-output", "--ext-output", "--dump-dir")
# --sd-bootloader builds dual-boot Sylverb's SD bootloader here.
SD_BOOTLOADER = 0x0803_2000


class PatchError(Exception):
    pass


def _option(argv: Sequence[str], name: str) -> bool:
    return any(a == name or a.startswith(name + "=") for a in argv)


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
    if not _option(argv, "--device"):
        raise PatchError("No model given: flash-patch mario|zelda|amalgam.")
    cmd = Command(argv)
    cmd.bootloader_repo = _pop_value(argv, "--bootloader-repo") or cmd.bootloader_repo
    cmd.bootloader_tag = _pop_value(argv, "--bootloader-tag") or cmd.bootloader_tag
    argv[:] = ["--sd-bootloader" if a == "--bootloader" else a for a in argv]
    if "--no-second-beep" in argv:
        argv.remove("--no-second-beep")
        log.warning("--no-second-beep is now a setting in the clock menu; ignoring it.")

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
    model = options.build_parser().parse_known_args(argv)[0].device
    if model not in MODELS:
        raise PatchError(f"{model} reads its backups from --backup-dir.")
    backups = work_dir / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(internal, backups / f"internal_flash_backup_{model}.bin")
    shutil.copyfile(external, backups / f"flash_backup_{model}.bin")
    argv.append(f"--backup-dir={backups}")
    return cmd


def patch_command(argv: Sequence[str], work_dir: Path) -> Command:
    """The patcher's command line: ``argv`` plus the defaults gnwmanager supplies.

    The old form translated (``_legacy()``), and the prebuilt ELFs (``unpack_elfs()``'s), output and debug files in ``work_dir`` (unless
    given).
    """
    cmd = _legacy(list(argv), work_dir)
    argv = cmd.argv
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


@dataclass
class _Option:
    """A patcher option, merged over the models that have it."""

    action: argparse.Action
    group: str
    # By model:
    defaults: dict[str, Any] = field(default_factory=dict)
    helps: dict[str, str] = field(default_factory=dict)


def _patcher_options(models: Sequence[str]) -> dict[str, _Option]:
    """``models``' patcher options, by option name, in the order the patcher's help lists them."""
    from gnwmanager.gnw_patch.patches import Device, options

    out: dict[str, _Option] = {}
    for model in models:
        parser = options.build_parser()
        Device.registry[model].add_arguments(parser)
        for group in parser._action_groups:
            for action in group._group_actions:
                option = out.setdefault(action.option_strings[-1], _Option(action, group.title or ""))
                option.defaults[model] = action.default
                option.helps[model] = (action.help or "").rstrip(".") + "."
    return out


def _help(name: str, option: _Option, models: Sequence[str]) -> str:
    """The option's help (each model's, if they differ), the models that have it, and its default if meaningful here."""
    if len(set(option.helps.values())) == 1:
        parts = [next(iter(option.helps.values()))]
    else:
        parts = [f"{m.capitalize()}: {h}" for m, h in option.helps.items()]
    if len(option.helps) < len(models):
        parts.append(" and ".join(m.capitalize() for m in option.helps) + " only.")
    defaults = {
        m: d for m, d in option.defaults.items() if isinstance(d, (int, float, str)) and not isinstance(d, bool)
    }
    # gnwmanager picks the device and the paths.
    if defaults and name != "--device" and name not in ADVANCED_OPTIONS:
        if len(set(defaults.values())) == 1:
            parts.append(f"Default: {next(iter(defaults.values()))}.")
        else:
            parts.append("Default: " + ", ".join(f"{d} ({m.capitalize()})" for m, d in defaults.items()) + ".")
    return " ".join(parts)


# flash-patch's options, by python name: (option name, nargs), so ``_patcher_argv()`` can
# give ``patch_command()`` back the ones on the command line (cyclopts passes only those).
_ARGV_OPTIONS: dict[str, tuple[str, Any]] = {}


def _signature(device: str) -> inspect.Signature:
    """A ``flash-patch`` command's parameters: ``device``'s patcher options, grouped as its help groups them.

    The amalgam takes every model's options. Cyclopts parses and documents them; the patcher still checks them (ranges, conflicts).
    """
    models = (device,) if device in MODELS else MODELS
    groups: dict[str, Group] = {}

    def group(title: str) -> Group:
        return groups.setdefault(title, Group(title, sort_key=len(groups)))

    group("Patch")
    kw = inspect.Parameter.KEYWORD_ONLY
    params = []
    if device != "amalgam":
        for name, what in (("internal", "internal"), ("external", "external flash")):
            help = f"Stock {what} backup, instead of the one in --backup-dir."
            annotation = Annotated[Optional[str], Parameter(name=name.upper(), help=help)]
            params.append(
                inspect.Parameter(name, inspect.Parameter.POSITIONAL_ONLY, default=None, annotation=annotation)
            )
    for name, option in _patcher_options(models).items():
        action = option.action
        if isinstance(action, argparse._HelpAction) or name == "--device":
            continue
        dest = action.dest
        if name in ADVANCED_OPTIONS:
            title = "Advanced"
        elif option.group == "options":
            title = "Patch"
        else:
            title = option.group
        kwargs: dict[str, Any] = {}
        if isinstance(action, argparse._StoreTrueAction):
            hint: Any = bool
            default: Any = False
        elif action.nargs in ("*", "+"):
            hint, default = Optional[list[str]], None
            kwargs["consume_multiple"] = True
        elif action.choices:
            hint, default = Optional[Literal[tuple(action.choices)]], None  # type: ignore[valid-type]
        else:
            hint, default = Optional[str], None
        param = Parameter(
            name=name,
            group=group(title),
            help=_help(name, option, models),
            show=name not in HIDDEN_OPTIONS,
            show_default=False,
            negative=(),
            **kwargs,
        )
        _ARGV_OPTIONS[dest] = (name, action.nargs)
        params.append(inspect.Parameter(dest, kw, default=default, annotation=Annotated[hint, param]))
        if name == "--sd-bootloader":
            bootloader = group(title)
            _ARGV_OPTIONS["bootloader_repo"] = ("--bootloader-repo", None)
            _ARGV_OPTIONS["bootloader_tag"] = ("--bootloader-tag", None)
            params += [
                inspect.Parameter(
                    "bootloader_repo",
                    kw,
                    default=BOOTLOADER_REPO,
                    annotation=Annotated[str, Parameter(group=bootloader, help="GitHub repo of the SD bootloader.")],
                ),
                inspect.Parameter(
                    "bootloader_tag",
                    kw,
                    default="latest",
                    annotation=Annotated[str, Parameter(group=bootloader, help="SD bootloader release to flash.")],
                ),
            ]
    # The old form's options, translated by _legacy().
    for dest, name in (("bootloader", "--bootloader"), ("no_second_beep", "--no-second-beep")):
        _ARGV_OPTIONS[dest] = (name, 0)
        params.append(inspect.Parameter(dest, kw, default=False, annotation=Annotated[bool, Parameter(show=False)]))
    params.append(
        inspect.Parameter(
            "backend_factory", kw, annotation=Annotated[Callable[[], dict[str, Any]], Parameter(parse=False)]
        )
    )
    return inspect.Signature(params)


def _patcher_argv(device: str, paths: Sequence[str], given: dict[str, Any]) -> list[str]:
    """The command line a ``flash-patch`` command got, as ``patch_command()`` takes it."""
    argv = [device, *paths]
    for dest, (name, nargs) in _ARGV_OPTIONS.items():
        value = given.get(dest)
        if value is None or value is False:
            continue
        if value is True:
            argv.append(name)
        elif nargs in ("*", "+"):
            argv += [name, *value]
        else:
            argv.append(f"{name}={value}")
    return argv


def flash_patch(
    device: str, paths: Sequence[str], backend_factory: Callable[[], dict[str, Any]], given: dict[str, Any]
):
    """Patches ``device``'s stock firmware and flashes it."""
    from gnwmanager.gnw_patch.patches import cli, options

    argv = _patcher_argv(device, paths, given)

    with tempfile.TemporaryDirectory() as tmp:
        try:
            cmd = patch_command(argv, Path(tmp))
            if not any(_option(argv, o) for o in CODE_OPTIONS):
                unpack_elfs(Path(tmp) / "patch_elfs")
        except PatchError as e:
            raise SystemExit(str(e)) from None
        cli.main(cmd.argv)  # Exits on a bad option.

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


HELP = """Patch the stock firmware for dual-boot (game-and-watch-patch) and flash it.

It reads the stock backups from ``--backup-dir`` (default: the current directory):
``internal_flash_backup_<model>.bin`` and ``flash_backup_<model>.bin``, or for ``mario`` and
``zelda``, the INTERNAL EXTERNAL arguments. ``amalgam`` puts both models in one image and needs
all 4 backups. ``flash-patch MODEL --help`` lists the model's options. ``--sd-bootloader`` also
flashes Sylverb's SD bootloader. The unit is connected only after patching succeeds.

Example::

    gnwmanager flash-patch zelda --sd-bootloader -- start bank1

https://github.com/BrianPugh/game-and-watch-patch
"""


def _command(device: str) -> Callable[..., None]:
    """The ``flash-patch`` command for ``device``."""

    def command(*paths: str, backend_factory: Callable[[], dict[str, Any]], **given: Any):
        flash_patch(device, paths, backend_factory, given)

    command.__name__ = f"flash_patch_{device}"
    if device == "amalgam":
        command.__doc__ = "Patch both models' stock firmware into one image (reads all 4 backups from --backup-dir)."
    else:
        command.__doc__ = f"Patch {device.capitalize()}'s stock firmware (INTERNAL EXTERNAL, or from --backup-dir)."
    command.__signature__ = _signature(device)  # type: ignore[attr-defined]
    command.__annotations__ = {name: p.annotation for name, p in command.__signature__.parameters.items()}  # type: ignore[attr-defined]
    return command


patch_app = App(name="flash-patch", help=HELP, version_flags=[], group_commands="Commands")
COMMANDS = {device: _command(device) for device in DEVICES}
for _device in DEVICES:
    patch_app.command(COMMANDS[_device], name=_device)
app.command(patch_app)
