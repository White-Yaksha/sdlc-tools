"""Prompt template loader for SDLC Tools."""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


def get_default_prompt() -> str:
    """Read the bundled default prompt template."""
    return (_PROMPTS_DIR / "default.txt").read_text(encoding="utf-8")


def load_prompt(prompt_file: str = "") -> str:
    """Load a prompt from a user-specified file, falling back to the default.

    Args:
        prompt_file: Path to a custom prompt file. If empty or the file
            does not exist, the bundled default is returned.

    Returns:
        The prompt text.
    """
    if prompt_file:
        path = Path(prompt_file).expanduser()
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return get_default_prompt()
