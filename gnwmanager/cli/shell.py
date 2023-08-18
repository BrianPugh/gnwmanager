import readline
import shlex

from typer import Option
from typing_extensions import Annotated

from gnwmanager.cli._parsers import int_parser
from gnwmanager.filesystem import get_filesystem


def shell(
    offset: Annotated[
        int,
        Option(
            min=0,
            parser=int_parser,
            help="Distance in bytes from the END of the filesystem, to the END of flash.",
        ),
    ] = 0,
):
    """Launch an interactive shell to browse device filesystem."""
    from .main import app, session

    target = session.target
    get_filesystem(target, offset=offset)

    print("Interactive shell. Press Ctrl-D to exit.")

    while True:
        try:
            user_input = input("gnw$ ")
        except EOFError:
            return
        if not user_input:
            continue

        split_user_input = shlex.split(user_input)

        if "--offset" not in split_user_input:
            split_user_input.extend(["--offset", str(offset)])

        try:
            app(args=split_user_input, standalone_mode=False)
        except Exception as e:
            print(e)
            continue
