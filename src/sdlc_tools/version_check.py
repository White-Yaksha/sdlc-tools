"""Check PyPI for newer versions of sdlc-tools."""

from __future__ import annotations

import click
import requests

from sdlc_tools import __version__

_PYPI_URL = "https://pypi.org/pypi/sdlc-tools/json"
_TIMEOUT = 3  # seconds — keep CLI snappy


def check_for_update() -> None:
    """Print a notice if a newer version is available on PyPI.

    Silently does nothing on network errors, timeouts, or unexpected
    responses so it never blocks normal CLI usage.
    """
    try:
        resp = requests.get(_PYPI_URL, timeout=_TIMEOUT)
        resp.raise_for_status()
        latest = resp.json()["info"]["version"]
    except Exception:
        return

    if latest != __version__:
        click.echo(
            click.style(
                f"[UPDATE] sdlc-tools {latest} is available "
                f"(current: {__version__}).  "
                f"Run: pip install --upgrade sdlc-tools",
                fg="yellow",
            ),
            err=True,
        )
