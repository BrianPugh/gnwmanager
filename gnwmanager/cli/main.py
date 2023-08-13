import sys
from collections import namedtuple

import typer
from pyocd.core.helpers import ConnectHelper
from pyocd.core.session import Session
from pyocd.core.target import Target
from typer import Option

import gnwmanager

from . import flash

session: Session
target: Target

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False, add_completion=False)
app.add_typer(flash.app, name="flash", chain=False)

Variable = namedtuple("Variable", ["address", "size"])

comm = {
    "framebuffer": Variable(0x2400_0000, 320 * 240 * 2),
    "flashapp_comm": Variable(0x2402_5800, 0xC4000),
}
contexts = [{} for i in range(2)]


def _populate_comm():
    # Communication Variables; put in a function to prevent variable leakage.
    comm["flashapp_state"] = last_variable = Variable(comm["flashapp_comm"].address, 4)
    comm["program_status"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
    comm["utc_timestamp"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
    comm["program_chunk_idx"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
    comm["program_chunk_count"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
    comm["active_context_index"] = last_variable = Variable(last_variable.address + last_variable.size, 4)

    for i in range(2):
        struct_start = comm["flashapp_comm"].address + ((i + 1) * 4096)
        contexts[i]["ready"] = last_variable = Variable(struct_start, 4)
        contexts[i]["size"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        contexts[i]["address"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        contexts[i]["erase"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        contexts[i]["erase_bytes"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        contexts[i]["decompressed_size"] = last_variable = Variable(last_variable.address + last_variable.size, 4)
        contexts[i]["expected_sha256"] = last_variable = Variable(last_variable.address + last_variable.size, 32)
        contexts[i]["expected_sha256_decompressed"] = last_variable = Variable(
            last_variable.address + last_variable.size, 32
        )

        # Don't ever directly use this, just here for alignment purposes
        contexts[i]["__buffer_ptr"] = last_variable = Variable(last_variable.address + last_variable.size, 4)

    struct_start = comm["flashapp_comm"].address + (3 * 4096)
    comm["active_context"] = last_variable = Variable(struct_start, 4096)

    for i in range(2):
        contexts[i]["buffer"] = last_variable = Variable(last_variable.address + last_variable.size, 256 << 10)


_populate_comm()


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

    global session, target
    with ConnectHelper.session_with_chosen_probe(options=options) as session:
        target = session.target
        assert target is not None
        for args in commands_args:
            app(args=args, standalone_mode=False)
