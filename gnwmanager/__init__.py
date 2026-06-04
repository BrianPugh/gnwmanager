import importlib.metadata

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:  # Package isn't installed (e.g. raw source tree).
    __version__ = "0.0.0"

__all__ = []

from gnwmanager.gnw import GnW
