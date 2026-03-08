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
        encoding="utf-8",
        errors="replace",
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
        encoding="utf-8",
        errors="replace",
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
        encoding="utf-8",
        errors="replace",
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
            encoding="utf-8",
            errors="replace",
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
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return ""


def push_current_branch(force: bool = False) -> bool:
    """Push the current branch to origin. Returns True on success."""
    branch = get_current_branch()
    log.info("Pushing branch '%s' to origin...", branch)
    cmd = ["git", "push", "-u", "origin", branch]
    if force:
        cmd.insert(2, "--force")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        log.error("Git push failed: %s", result.stderr.strip())
        return False
    log.info("Push successful.")
    return True


def get_last_commit_sha() -> str:
    """Return the full SHA of HEAD."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        log.error("Failed to get HEAD SHA: %s", result.stderr.strip())
        sys.exit(1)
    return result.stdout.strip()


def get_short_sha(sha: str) -> str:
    """Return the first 7 characters of a SHA."""
    return sha[:7]


def get_commit_diff(sha: str) -> str:
    """Return the diff introduced by a single commit."""
    result = subprocess.run(
        ["git", "diff", f"{sha}~1..{sha}"],
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        log.error(
            "Failed to get diff for commit %s: %s",
            sha[:7], result.stderr.strip(),
        )
        sys.exit(1)
    return result.stdout
