from time import sleep

from pyocd.gdbserver import GDBServer
from pyocd.utility.color_log import build_color_logger
from typer import Option
from typing_extensions import Annotated


def gdbserver(
    port: Annotated[int, Option(help="GDB Server Port")] = 3333,
):
    """Launch a gdbserver."""
    from .main import session

    session.options.set("gdbserver_port", port)

    build_color_logger(level=1)

    gdb = GDBServer(session, core=0)
    session.gdbservers[0] = gdb
    gdb.start()

    while gdb.is_alive():
        sleep(0.1)
