import argparse
from enum import Enum
from typing import Optional

import typer
from typer import Option
from typing_extensions import Annotated

import gnwmanager
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

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False, add_completion=False)
app.add_typer(debug.app, name="debug")
app.add_typer(screenshot.app, name="screenshot")
app.command()(disable_debug.disable_debug)
app.command()(erase.erase)
app.command()(flash.flash)
app.command()(format.format)
app.command()(gdb.gdb)
app.command()(gdbserver.gdbserver)
app.command()(ls.ls)
app.command()(mkdir.mkdir)
app.command()(monitor.monitor)
app.command()(mv.mv)
app.command()(pull.pull)
app.command()(push.push)
app.command()(shell.shell)
app.command()(start.start)
app.command()(tree.tree)
app.command()(unlock.unlock)


def version_callback(value: bool):
    if not value:
        return
    print(gnwmanager.__version__)
    raise typer.Exit()


OCDBackendEnum = Enum("OCDBackendEnum", ((x, x) for x in OCDBackend))


@app.callback()
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

    # Easier for all downstream typehinting, it's only ever None
    # early in the process.
    gnw = None  # pyright: ignore [reportGeneralTypeIssues]

    early_parser = argparse.ArgumentParser(add_help=False)
    early_parser.add_argument(
        "--backend",
        "-b",
        type=str.lower,
        default=OCDBackendEnum.pyocd.value,  # pyright: ignore [reportGeneralTypeIssues]
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

    for i, args in enumerate(commands_args):
        is_last = i == (len(commands_args) - 1)
        if not args or "--help" in args or "--version" in args:
            # Early help and version print without having to session
            app(args=args, prog_name="gnwmanager")

        command = args[0]
        if command in ("shell", "gdb", "monitor", "gdbserver", "unlock") and not is_last:
            raise ValueError(f'Command "{command}" must be the final chained command.')

    connect_mode = "attach"  # "halt" if commands_args[-1][0] == "unlock" else "attach"

    with OCDBackend[early_args.backend](connect_mode) as backend:
        gnw = GnW(backend)
        if len(commands_args) == 1 and (
            (commands_args[0][0] in ("monitor", "gdb", "gdbserver", "start", "disable-debug"))
            or (commands_args[0][:2] == ["screenshot", "capture"])
        ):
            # Do NOT start the on-device app
            pass
        else:
            start_gnwmanager()

        for args in commands_args:
            app(args=args, standalone_mode=False, prog_name="gnwmanager")
