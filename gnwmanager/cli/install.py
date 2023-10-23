import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from autoregistry import Registry
from typer import Argument, Context, Option
from typing_extensions import Annotated

installable_programs = Registry()


def _install_from_available_package_manager(install_cmds: Dict[str, List[List[str]]]):
    for manager, cmds in install_cmds.items():
        if shutil.which(manager) is not None:
            for cmd in cmds:
                subprocess.check_call(cmd)
            return

    print(f"Supported package manager not found. Must have one of {set(install_cmds.keys())}")
    sys.exit(1)


@installable_programs
def openocd(platform: str):
    install_cmds = {
        "linux": {
            "apt-get": [["sudo", "apt-get", "update"], ["sudo", "apt-get", "install", "openocd"]],
            "pacman": [["sudo", "pacman", "-Sy", "openocd"]],
            "yum": [["sudo", "yum", "install", "openocd"]],
            "dnf": [["sudo", "dnf", "install", "openocd"]],
            "zypper": [["sudo", "zypper", "install", "openocd"]],
        },
        "darwin": {
            "brew": [["brew", "install", "openocd"]],
        },
        "win32": {
            "choco": [["choco", "install", "openocd"]],
        },
    }

    _install_from_available_package_manager(install_cmds[platform])


def install(
    ctx: Context,
    programs: Annotated[Optional[List[Path]], Argument(help="Programs to install")] = None,
    show: Annotated[
        bool,
        Option(
            "--show",
            help="Display available packages to install.",
        ),
    ] = False,
):
    """Install third party executables, like openocd."""
    if show:
        for program in sorted(installable_programs):
            print(program)
        return

    if programs is None:
        programs = []

    if not programs:
        ctx.get_help()
        return

    # First, make sure all provided programs are valid
    for program in programs:
        if program.name not in installable_programs:
            raise ValueError(f'Unknown program "{program}"')

    for program in programs:
        location = shutil.which(program.name)
        if location is not None:
            print(f"{program.name} already installed at {location}. Skipping...")
            continue

        # sys.platform is typically one of {"linux", "darwin", "win32"}
        installable_programs[program.name](sys.platform)
