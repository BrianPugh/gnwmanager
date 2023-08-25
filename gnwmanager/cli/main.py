import sys

import typer
from pyocd.core.helpers import ConnectHelper
from pyocd.core.session import Session
from typer import Option

import gnwmanager
from gnwmanager.target import GnWTargetMixin, mixin_object

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

session: Session

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
    version: bool = Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        help="Print gnwmanager version.",
    ),
):
    pass


def run_app():
    global app, session
    options = {
        "frequency": 5_000_000,
        "connect_mode": "attach",
        "warning.cortex_m_default": False,
        "persist": True,
        "target_override": "STM32H7B0xx",
    }

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
            # Early help and version print without having to launch device
            app(args=args, prog_name="gnwmanager")

        command = args[0]
        if command in ("shell", "gdb", "monitor", "gdbserver") and not is_last:
            raise ValueError(f'Command "{command}" must be the final chained command.')

    global session
    with ConnectHelper.session_with_chosen_probe(options=options) as session:
        # Hack in our convenience methods
        mixin_object(session.target, GnWTargetMixin)

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
