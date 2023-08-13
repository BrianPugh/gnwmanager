import sys

import typer
from pyocd.core.helpers import ConnectHelper
from pyocd.core.session import Session
from typer import Option

import gnwmanager
from gnwmanager.target import GnWTargetMixin, mixin_object

from . import flash, start

session: Session

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False, add_completion=False)
app.add_typer(flash.app, name="flash")
app.command()(start.start)


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
    global session
    options = {
        "frequency": 5_000_000,
        "connect_mode": "attach",
        "warning.cortex_m_default": False,
        "target_override": "STM32H7B0",
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

    global session
    with ConnectHelper.session_with_chosen_probe(options=options) as session:
        # Hack in our convenience methods
        mixin_object(session.target, GnWTargetMixin)

        for args in commands_args:
            app(args=args, standalone_mode=False)
