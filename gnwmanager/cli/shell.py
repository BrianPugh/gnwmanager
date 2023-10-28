from contextlib import suppress

with suppress(ImportError):
    import readline  # Not available on windows

import os
import shlex

from typer import Option
from typing_extensions import Annotated

from gnwmanager.cli._parsers import int_parser


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
    from .main import app, gnw

    if os.name == "posix":
        print("Interactive shell. Press Ctrl-D to exit.")
    else:  # Windows
        print("Interactive shell. Press Ctrl-Z followed by Enter to exit.")

    while True:
        try:
            user_input = input("gnw$ ")
        except EOFError:
            return
        if not user_input:
            continue

        split_user_input = shlex.split(user_input)

        if split_user_input[0] in ("q", "quit"):
            break

        if "--offset" not in split_user_input:
            split_user_input.extend(["--offset", str(offset)])

        try:
            app(args=split_user_input, standalone_mode=False)
        except Exception as e:
            print(e)
            continue
