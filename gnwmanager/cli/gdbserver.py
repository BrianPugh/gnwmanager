from typer import Option
from typing_extensions import Annotated


def gdbserver(
    port: Annotated[int, Option(help="GDB Server Port")] = 3333,
):
    """Launch a gdbserver."""
    from .main import gnw

    gnw.backend.start_gdbserver(port)
