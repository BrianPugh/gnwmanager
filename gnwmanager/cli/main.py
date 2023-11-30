import argparse
import logging
import platform
import shutil
import sys
from enum import Enum
from typing import Optional

import cyclopts
import typer
from typer import Option
from typing_extensions import Annotated

import gnwmanager
from gnwmanager import __version__
from gnwmanager.cli._parsers import int_parser
from gnwmanager.cli._start_gnwmanager import start_gnwmanager
from gnwmanager.gnw import GnW
from gnwmanager.ocdbackend import OCDBackend

from . import (
    debug,
    disable_debug,
    erase,
    flash,
    format,
    gdb,
    gdbserver,
    info,
    install,
    lock,
    ls,
    mkdir,
    monitor,
    mv,
    pull,
    push,
    screenshot,
    shell,
    start,
    tree,
    unlock,
)

gnw: GnW

typer_app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
typer_app.add_typer(debug.app, name="debug")
typer_app.add_typer(screenshot.app, name="screenshot")
typer_app.command()(disable_debug.disable_debug)
typer_app.command()(erase.erase)
typer_app.command()(flash.flash)
typer_app.command()(format.format)
typer_app.command()(info.info)
typer_app.command()(gdb.gdb)
typer_app.command()(gdbserver.gdbserver)
typer_app.command()(install.install)
typer_app.command()(lock.lock)
typer_app.command()(ls.ls)
typer_app.command()(mkdir.mkdir)
typer_app.command()(monitor.monitor)
typer_app.command()(mv.mv)
typer_app.command()(pull.pull)
typer_app.command()(push.push)
typer_app.command()(shell.shell)
typer_app.command()(start.start)
typer_app.command()(tree.tree)
typer_app.command()(unlock.unlock)


def version_callback(value: bool):
    if not value:
        return
    print(gnwmanager.__version__)
    raise typer.Exit()


OCDBackendEnum = Enum("OCDBackendEnum", ((x, x) for x in OCDBackend))


def _display_host_info(backend):
    """Display Host-side information.

    Useful for debugging
    """
    info.display("Platform:", platform.platform(aliased=True))
    info.display("Python Version:", sys.version)
    info.display("GnWManager Executable:", shutil.which(sys.argv[0]))
    info.display("GnWManager Version:", __version__)
    info.display("OCD Backend:", backend)


@typer_app.callback()
def common(
    ctx: typer.Context,
    version: Annotated[
        bool,
        Option(
            "--version",
            "-v",
            callback=version_callback,
            help="Print gnwmanager version.",
        ),
    ] = False,
    frequency: Annotated[
        Optional[int],
        Option("--frequency", "-f", parser=int_parser, help="Probe frequency."),
    ] = None,
    backend: Annotated[
        OCDBackendEnum,
        Option("--backend", "-b", help="OCD Backend."),
    ] = OCDBackendEnum.pyocd.value,  # pyright: ignore [reportGeneralTypeIssues]
):
    """Game And Watch Device Manager.

    Manages device flashing, filesystem management, peripheral configuration, and more.
    """
    # This callback gets invoked before each command.
    # Note: ``backend`` here is just for help string, it's actually parsed/used by argparse.

    global gnw
    if gnw and frequency:
        gnw.backend.set_frequency(frequency)


def run_app():
    global gnw

    # Suppresses log messages like:
    #    * "Invalid coresight component"
    #    * "Error attempting to probe CoreSight component referenced by ROM table entry #5"
    logging.getLogger("pyocd").setLevel(logging.CRITICAL)

    # Easier for all downstream typehinting, it's only ever None
    # early in the process.
    gnw = None  # pyright: ignore [reportGeneralTypeIssues]

    early_parser = argparse.ArgumentParser(add_help=False)
    early_parser.add_argument(
        "--backend",
        "-b",
        type=str.lower,
        default=OCDBackendEnum.openocd.value,  # pyright: ignore [reportGeneralTypeIssues]
    )
    early_args, sys_args = early_parser.parse_known_args()

    # Manual command chaining; Typer/Clicks's builtin is kinda broken.
    commands_args = []
    current_command_args = []
    for arg in sys_args:
        if arg == "--":
            commands_args.append(current_command_args)
            current_command_args = []
        else:
            current_command_args.append(arg)
    commands_args.append(current_command_args)

    filtered_commands_args = []
    for i, args in enumerate(commands_args):
        is_last = i == (len(commands_args) - 1)
        if not args or {"-v", "--version", "-h", "--help"}.intersection(args):
            # Early help and version print without having to session
            typer_app(args=args, prog_name="gnwmanager")

        command = args[0]

        # Commands that don't interact with device
        if command in ("install"):
            typer_app(args=args, prog_name="gnwmanager")
            continue

        # Commands that must be standalone/last.
        if command in ("shell", "gdb", "monitor", "gdbserver", "unlock", "lock", "info") and not is_last:
            raise ValueError(f'Command "{command}" must be the final chained command.')

        filtered_commands_args.append(args)

    if not filtered_commands_args:
        return

    if filtered_commands_args[-1][0] == "info":
        _display_host_info(early_args.backend)

    with OCDBackend[early_args.backend]() as backend:
        gnw = GnW(backend)
        if len(filtered_commands_args) == 1 and (
            (filtered_commands_args[0][0] in ("monitor", "gdb", "gdbserver", "start", "disable-debug"))
            or (filtered_commands_args[0][:2] == ["screenshot", "capture"])
        ):
            # Do NOT start the on-device app
            pass
        else:
            start_gnwmanager()

        for args in filtered_commands_args:
            typer_app(args=args, standalone_mode=False, prog_name="gnwmanager")
