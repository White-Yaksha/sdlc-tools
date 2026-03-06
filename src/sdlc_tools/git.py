"""Git operations — branch, diff, remote, and commit helpers."""

from __future__ import annotations

import re
import subprocess
import sys

from sdlc_tools.log import get_logger

log = get_logger("git")

_TIMEOUT = 30


def get_current_branch() -> str:
    """Return the current git branch name."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
    )
    if result.returncode != 0:
        log.error("Failed to detect current branch: %s", result.stderr.strip())
        sys.exit(1)
    return result.stdout.strip()


def get_diff(base_branch: str) -> str:
    """Generate git diff between ``origin/<base_branch>`` and ``HEAD``.

    Fetches the base branch first to ensure accuracy.
    """
    fetch_branch(base_branch)
    result = subprocess.run(
        ["git", "diff", f"origin/{base_branch}...HEAD"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        log.error("Failed to generate diff: %s", result.stderr.strip())
        sys.exit(1)
    return result.stdout


def fetch_branch(branch: str) -> None:
    """Fetch a branch from origin. Warns on failure but does not abort."""
    result = subprocess.run(
        ["git", "fetch", "origin", branch],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        log.warning("Failed to fetch origin/%s: %s", branch, result.stderr.strip())


def get_repo_url() -> str:
    """Parse ``owner/repo`` from the git remote origin URL.

    Falls back to the ``GITHUB_REPOSITORY`` environment variable.
    """
    import os

    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        url = result.stdout.strip()
        match = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
        if match:
            return match.group(1)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return os.environ.get("GITHUB_REPOSITORY", "")


def get_latest_commit_message() -> str:
    """Return the subject line of the latest commit."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return ""
