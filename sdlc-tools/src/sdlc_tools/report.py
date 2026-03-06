"""AI code impact report generation and PR comment posting."""

from __future__ import annotations

import re
import subprocess
import sys

from sdlc_tools.ai import get_provider
from sdlc_tools.client import GitHubClient
from sdlc_tools.config import SdlcConfig
from sdlc_tools.git import get_current_branch, get_diff, get_latest_commit_message, get_repo_url
from sdlc_tools.html import convert_markdown_to_html
from sdlc_tools.log import get_logger

log = get_logger("report")


class ReportGenerator:
    """Generates AI code impact reports and posts them to GitHub PRs."""

    def __init__(self, client: GitHubClient, config: SdlcConfig) -> None:
        self.client = client
        self.config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Full workflow: generate diff → AI analysis → post to PR."""
        repo_full = self.config.github_repository or get_repo_url()
        if not repo_full or "/" not in repo_full:
            log.error("Could not determine repository (owner/repo).")
            sys.exit(1)

        owner, repo = repo_full.split("/", 1)
        branch = get_current_branch()
        log.info("Branch: %s", branch)

        if branch == self.config.base_branch:
            log.info("On base branch '%s'. Nothing to report.", self.config.base_branch)
            return

        # Generate diff.
        diff = get_diff(self.config.base_branch)
        if not diff.strip():
            log.info("No diff detected. Nothing to report.")
            return

        log.info("Diff length: %d characters.", len(diff))

        # Truncate if needed.
        max_len = self.config.max_diff_length
        if len(diff) > max_len:
            log.info("Truncating diff from %d to %d characters.", len(diff), max_len)
            diff = diff[:max_len] + "\n\n... (diff truncated)"

        # Run AI analysis via configured provider.
        try:
            provider = get_provider(self.config)
        except ValueError as exc:
            log.error("%s", exc)
            sys.exit(1)

        log.info("Using AI provider: %s", provider.name)

        if self.config.dry_run:
            log.info("[DRY-RUN] Would invoke %s with %d-char prompt.", provider.name, len(diff))
            return

        try:
            markdown_report = provider.analyze(self.config.prompt_template, diff)
        except RuntimeError as exc:
            log.error("AI analysis failed: %s", exc)
            sys.exit(1)

        if not markdown_report:
            log.warning("AI provider returned empty response. Skipping report.")
            return

        # Convert to HTML.
        html_report = convert_markdown_to_html(
            markdown_report,
            marker=self.config.comment_marker,
        )

        # Post to PR.
        self._post_to_pr(owner, repo, branch, html_report)

    # ------------------------------------------------------------------
    # PR interaction
    # ------------------------------------------------------------------

    def _post_to_pr(self, owner: str, repo: str, branch: str, html: str) -> None:
        """Find (or create) the PR and post/update the AI report comment."""
        pr_number = self.client.find_pr(owner, repo, branch)

        if pr_number is None:
            log.info("No open PR found for branch '%s'. Creating draft PR...", branch)
            pr_number = self._create_draft_pr(owner, repo, branch)
            if pr_number is None:
                log.warning("Could not create PR. Skipping comment post.")
                return

        log.info("PR number: #%d", pr_number)

        # Post or update comment (idempotent via marker).
        existing_id = self.client.find_comment_by_marker(
            owner, repo, pr_number, self.config.comment_marker,
        )
        if existing_id:
            self.client.update_comment(owner, repo, existing_id, html)
        else:
            self.client.create_comment(owner, repo, pr_number, html)

        log.info("AI report generation complete.")

    def _create_draft_pr(self, owner: str, repo: str, branch: str) -> int | None:
        """Create a draft PR via ``gh`` CLI to preserve developer identity."""
        repo_full = f"{owner}/{repo}"
        title = get_latest_commit_message() or branch

        if self.config.dry_run:
            log.info("[DRY-RUN] Would create draft PR '%s' on %s.", title, repo_full)
            return None

        try:
            result = subprocess.run(
                [
                    "gh", "pr", "create",
                    "--repo", repo_full,
                    "--draft",
                    "--base", self.config.base_branch,
                    "--head", branch,
                    "--title", title,
                    "--body", "Auto-generated PR created by SDLC automation.",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            log.error("Failed to run gh pr create: %s", exc)
            return None

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "already exists" in stderr.lower():
                log.info("PR already exists. Retrying lookup...")
                return self.client.find_pr(owner, repo, branch)
            log.error("gh pr create failed: %s", stderr)
            return None

        url = result.stdout.strip()
        match = re.search(r"/pull/(\d+)", url)
        if match:
            pr_num = int(match.group(1))
            log.info("Created draft PR #%d: %s", pr_num, url)
            return pr_num

        log.warning("PR created but could not parse number from: %s", url)
        return None
