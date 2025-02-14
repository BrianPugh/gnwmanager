from pathlib import Path
from time import sleep
from typing import Optional

from cyclopts import App, Parameter, validators
from cyclopts.types import ExistingDirectory
from typing_extensions import Annotated

from gnwmanager.cli._parsers import GnWType
from gnwmanager.cli.devices import DeviceModel
from gnwmanager.cli.main import app

app.command(boxart_app := App(name="boxart"))


@boxart_app.command
def auto(
    directory: ExistingDirectory,
):
    """Automatically download & Process Boxart."""
    raise NotImplementedError


@boxart_app.command
def resize():
    raise NotImplementedError
