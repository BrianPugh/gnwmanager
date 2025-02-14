import hashlib
import os
import sqlite3
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from importlib import resources
from pathlib import Path
from time import sleep
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests
from autoregistry import Registry
from cyclopts import App, Parameter, validators
from cyclopts.types import ExistingDirectory
from typing_extensions import Annotated

from gnwmanager.cli._parsers import GnWType
from gnwmanager.cli.devices import DeviceModel
from gnwmanager.cli.main import app, find_cache_folder

app.command(boxart_app := App(name="boxart"))


class SystemNotFoundError(Exception):
    pass


@dataclass
class System(Registry):
    extensions: list[str]
    dat_files: list[Path]

    @classmethod
    def from_path(cls, path: Path | str) -> "System":
        return cls.from_ext(Path(path).suffix)

    @classmethod
    def from_ext(cls, ext: str) -> "System":
        ext = ext.lower()
        if not ext.startswith("."):
            raise ValueError("Extensions must start with a period.")
        for system in System.values():
            if ext in system.extensions:
                return system
        raise SystemNotFoundError

    @classmethod
    @property
    def name(cls) -> str:
        return cls.__registry__.name

    def download_boxart(self, path: Path):
        raise NotImplementedError

    @classmethod
    def sha1(cls, path: Path | str, start=0) -> str:
        """Calculate SHA1 hash of file from start to end position"""
        if start < 0:
            raise ValueError("Start position cannot be negative")

        path = Path(path)
        engine = hashlib.sha1()

        with path.open("rb") as f:
            f.seek(start)
            for chunk in iter(lambda: f.read(4096), b""):
                engine.update(chunk)

        return engine.hexdigest()


class GameBoy(System):
    extensions = [".gb"]
    dat_files = [
        Path("no_intro/Nintendo - Game Boy (20250207-225721).dat"),
    ]


class GameBoyColor(System):
    extensions = [".gbc"]
    dat_files = [
        Path("no_intro/Nintendo - Game Boy Color (20250208-231842).dat"),
    ]


class Nes(System):
    extensions = [".nes"]
    dat_files = [
        Path("no_intro/Nintendo - Nintendo Entertainment System (Headered) (20250212-235144).dat"),
    ]

    @classmethod
    def sha1(cls, path: Path | str, start=16) -> str:
        return super().sha1(path, start=16)


class GameAndWatch(System):
    extensions = [".gw"]
    dat_files = [
        Path("no_intro/Nintendo - Game & Watch (20241105-120946).dat"),
    ]


class Genesis(System):
    extensions = [".md"]
    dat_files = [
        Path("no_intro/Sega - Mega Drive - Genesis (20250210-102212).dat"),
    ]


class MasterSystem(System):
    extensions = [".sms"]
    dat_files = [
        Path("no_intro/Sega - Master System - Mark III (20241225-050512).dat"),
    ]


class TurboGrafx(System):
    extensions = [".pce"]
    dat_files = [
        Path("no_intro/NEC - PC Engine - TurboGrafx-16 (20250121-134606).dat"),
    ]


class GameGear(System):
    extensions = [".gg"]
    dat_files = [
        Path("no_intro/Sega - Game Gear (20241203-185356).dat"),
    ]


class GameDB:
    def __init__(self, db_path: str = "gnwmanager.db"):
        self.db_path = db_path
        self._construct_tables()
        for system in System.values():
            self._load_dat_files(system)

    def _construct_tables(self):
        """Initialize SQLite database with necessary tables"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """\
                CREATE TABLE IF NOT EXISTS roms (
                    sha1 TEXT PRIMARY KEY NOT NULL,
                    system TEXT NOT NULL,
                    name TEXT,
                    last_modified TIMESTAMP
                )
                """
            )

            conn.execute(
                """\
                CREATE TABLE IF NOT EXISTS boxart_cache (
                    sha1 TEXT PRIMARY KEY,
                    image_path TEXT,
                    source TEXT,
                    last_modified TIMESTAMP,
                    FOREIGN KEY(sha1) REFERENCES roms(sha1)
                )
                """
            )
            conn.execute(
                """\
                CREATE TABLE IF NOT EXISTS dat_files (
                    file_path TEXT PRIMARY KEY,
                    system TEXT,
                    last_modified TIMESTAMP
                )
                """
            )

            conn.commit()

    def _load_dat_files(self, system: System):
        """Load dat files into DB (if needed)."""
        with resources.path("gnwmanager.cli", "_boxart_dat_files") as data_path, sqlite3.connect(self.db_path) as conn:
            for dat_file in system.dat_files:
                dat_file = (data_path / dat_file).absolute()
                print(dat_file)
                current_mtime = datetime.fromtimestamp(dat_file.stat().st_mtime)

                cursor = conn.execute("SELECT last_modified FROM dat_files WHERE file_path = ?", (str(dat_file),))
                result = cursor.fetchone()

                if result:
                    last_processed = datetime.fromisoformat(result[0])
                    if current_mtime <= last_processed:
                        continue

                tree = ElementTree.parse(dat_file)
                root = tree.getroot()
                conn.execute("BEGIN TRANSACTION")

                try:
                    for game in root.findall(".//game"):
                        rom = game.find("rom")
                        if rom is None:
                            continue
                        conn.execute(
                            """\
                            INSERT OR REPLACE INTO roms
                            (sha1, system, name, last_modified)
                            VALUES (?, ?, ?, ?)
                            """,
                            (
                                rom.get("sha1"),
                                system.name,
                                game.get("name"),
                                datetime.now().isoformat(),
                            ),
                        )
                    conn.execute(
                        """\
                        INSERT OR REPLACE INTO dat_files (file_path, system, last_modified)
                        VALUES (?, ?, ?)
                        """,
                        (str(dat_file), system.name, datetime.now().isoformat()),
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise

    def get_rom_info(self, path: Path | str) -> dict[str, Any]:
        """Get all available information for a ROM"""
        path = Path(path)
        system = System.from_path(path)
        sha1_hash = system.sha1(path)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT * FROM roms WHERE sha1 = ?", (sha1_hash,))
            info = cursor.fetchone()
        breakpoint()
        raise NotImplementedError


@boxart_app.command
def auto(
    directory: ExistingDirectory,
):
    """Automatically download & Process Boxart."""
    # cache_folder = find_cache_folder()
    game_db = GameDB()  # TODO: use cache_folder
    for path in directory.rglob("*.gb"):
        try:
            rom_info = game_db.get_rom_info(path)
        except SystemNotFoundError:
            continue
    breakpoint()
    raise NotImplementedError


@boxart_app.command
def resize():
    raise NotImplementedError
