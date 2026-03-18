"""SDLC Tools — A developer CLI toolkit for SDLC automation."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("sdlc-tools")
except PackageNotFoundError:
    __version__ = "0.0.0"
