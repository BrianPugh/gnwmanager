import sys
from contextlib import suppress
from typing import Optional

import typer
from typer import Option
from typing_extensions import Annotated

import gnwmanager
from gnwmanager.cli._parsers import int_parser
from gnwmanager.target import GnW, OCDBackend

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
)
from ._start_gnwmanager import start_gnwmanager

gnw: GnW

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False, add_completion=False)
app.add_typer(debug.app, name="debug")
app.add_typer(flash.app, name="flash")
app.add_typer(screenshot.app, name="screenshot")
app.command()(disable_debug.disable_debug)
app.command()(erase.erase)
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


def version_callback(value: bool):
    if not value:
        return
    print(gnwmanager.__version__)
    raise typer.Exit()


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
        Optional[float], Option("--frequency", "-f", parser=int_parser, help="Probe frequency.")
    ] = None,
):
    """Game And Watch Device Manager.

    Manages device flashing, filesystem management, peripheral configuration, and more.
    """
    # This callback gets invoked before each command.

    global gnw
    if gnw and frequency:
        gnw.probe.set_clock(frequency)


def _set_good_default_clock(probe):
    name = probe.product_name

    lookup = {
        "Picoprobe (CMSIS-DAP)": 10_000_000,
        "STM32 STLink": 10_000_000,
        "CMSIS-DAP_LU": 500_000,
    }

    with suppress(KeyError):
        probe.set_clock(lookup[name])


def run_app():
    global gnw

    # Manual command chaining; Typer/Clicks's builtin is kinda broken.
    sys_args = sys.argv[1:]
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
        if command in ("shell", "gdb", "monitor", "gdbserver") and not is_last:
            raise ValueError(f'Command "{command}" must be the final chained command.')

    # Frequency needs to be set prior to connecting.
    with OCDBackend["pyocd"]() as backend:  # TODO: determine backend from cli
        gnw = GnW(backend)
        if len(commands_args) == 1 and (
            (commands_args[0][0] in ("monitor", "gdb", "gdbserver"))
            or (commands_args[0][:2] == ["screenshot", "capture"])
        ):
            # Do NOT start the on-device app
            pass
        else:
            start_gnwmanager()

        for args in commands_args:
            app(args=args, standalone_mode=False, prog_name="gnwmanager")
