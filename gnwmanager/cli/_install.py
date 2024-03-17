import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

from autoregistry import Registry
from cyclopts import Parameter
from typing_extensions import Annotated

from gnwmanager.cli.main import app

installable_programs = Registry(hyphen=True)

log = logging.getLogger(__name__)


def _install_from_available_package_manager(install_cmds: Dict[str, List[List[str]]]):
    sudo_bin = shutil.which("sudo")
    for manager, cmds in install_cmds.items():
        if shutil.which(manager) is not None:
            for cmd in cmds:
                if sudo_bin is None:
                    # Strip out the "sudo" parts of command; common in a docker container.
                    cmd = [x for x in cmd if x != "sudo"]
                subprocess.check_call(cmd)
            return

    print(f"Supported package manager not found. Must have one of {set(install_cmds.keys())}")
    sys.exit(1)


@installable_programs
def openocd(platform: str):
    install_cmds = {
        "linux": {
            "apt-get": [["sudo", "apt-get", "update"], ["sudo", "apt-get", "-y", "install", "openocd"]],
            "pacman": [["sudo", "pacman", "-Sy", "--noconfirm", "openocd"]],
            "yum": [["sudo", "yum", "-y", "install", "openocd"]],
            "dnf": [["sudo", "dnf", "-y", "install", "openocd"]],
            "zypper": [["sudo", "zypper", "--non-interactive", "install", "openocd"]],
        },
        "darwin": {
            "brew": [["brew", "install", "openocd"]],
        },
        "win32": {
            "choco": [["choco", "install", "openocd", "-y"]],
        },
    }

    _install_from_available_package_manager(install_cmds[platform])


@installable_programs
def arm_toolchain(platform: str):
    install_cmds = {
        "linux": {
            "apt-get": [["sudo", "apt-get", "update"], ["sudo", "apt-get", "-y", "install", "gcc-arm-none-eabi"]],
            "pacman": [["sudo", "pacman", "-Sy", "--noconfirm", "arm-none-eabi-gcc"]],
            "yum": [["sudo", "yum", "-y", "install", "arm-none-eabi-newlib", "arm-none-eabi-gcc-cs"]],
            "dnf": [["sudo", "dnf", "-y", "install", "arm-none-eabi-newlib", "arm-none-eabi-gcc-cs"]],
            "zypper": [["sudo", "zypper", "--non-interactive", "install", "cross-arm-none-gcc-cs"]],
        },
        "darwin": {
            "brew": [["brew", "install", "arm-gcc-bin"]],
        },
        "win32": {
            "choco": [["choco", "install", "gcc-arm-embedded", "-y"]],
        },
    }

    _install_from_available_package_manager(install_cmds[platform])


@app.command
def install(
    *programs: Path,
    show: Annotated[bool, Parameter(negative=[], show_default=False)] = False,
):
    """Install third party executables, like openocd.

    Parameters
    ----------
    programs: Optional[List[Path]]
        Programs to install.
    show:
        Display available packages to install.
    """
    if show:
        for program in sorted(installable_programs):
            print(program)
        return

    if not programs:
        app.help_print(["install"])
        return

    # First, make sure all provided programs are valid
    for program in programs:
        if program.name not in installable_programs:
            raise ValueError(f'Unknown program "{program}"')

    logging.debug(f"{sys.platform=}")
    for program in programs:
        location = shutil.which(program.name)
        if location is not None:
            print(f"{program.name} already installed at {location}. Skipping...")
            continue
        logging.info(f"Installing {program.name}")

        # sys.platform is typically one of {"linux", "darwin", "win32"}
        installable_programs[program.name](sys.platform)
