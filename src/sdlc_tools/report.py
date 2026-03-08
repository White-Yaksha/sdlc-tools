"""AI code impact report generation and PR comment posting."""

from __future__ import annotations

import sys

from sdlc_tools.ai import get_provider
from sdlc_tools.client import GitHubClient
from sdlc_tools.config import SdlcConfig
from sdlc_tools.git import (
    get_commit_diff,
    get_current_branch,
    get_diff,
    get_latest_commit_message,
    get_repo_url,
    get_short_sha,
)
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

    def run(self, *, commit_sha: str | None = None) -> None:
        """Full workflow: generate diff → AI analysis → post to PR.

        If *commit_sha* is provided, analyses only that single commit and
        appends the report as a separate PR comment (idempotent per commit).
        """
        repo_full = self.config.github_repository or get_repo_url()
        if not repo_full or "/" not in repo_full:
            log.error("Could not determine repository (owner/repo).")
            sys.exit(1)

        owner, repo = repo_full.split("/", 1)
        branch = get_current_branch()
        log.info("Branch: %s", branch)

        if not commit_sha and branch == self.config.base_branch:
            log.info("On base branch '%s'. Nothing to report.", self.config.base_branch)
            return

        # Generate diff — full branch or single commit.
        if commit_sha:
            short = get_short_sha(commit_sha)
            log.info("Commit mode: %s", short)
            diff = get_commit_diff(commit_sha)
        else:
            diff = get_diff(self.config.base_branch)

        if not diff or not diff.strip():
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

        # Convert to HTML — commit reports get a distinct title and marker.
        provider_label = provider.display_name
        if commit_sha:
            short = get_short_sha(commit_sha)
            title = f"\U0001f50d Commit Impact Report \u2014 {short}"
            marker = f"<!-- AI-SDLC-COMMIT-{short} -->"
            subtitle = f"Commit: {commit_sha} | Provider: {provider_label}"
        else:
            title = "\U0001f50d AI Code Impact Report"
            marker = self.config.comment_marker
            subtitle = f"Provider: {provider_label}"

        html_report = convert_markdown_to_html(
            markdown_report,
            title=title,
            marker=marker,
            subtitle=subtitle,
        )

        # Post to PR.
        self._post_to_pr(owner, repo, branch, html_report, marker=marker)

    # ------------------------------------------------------------------
    # PR interaction
    # ------------------------------------------------------------------

    def _post_to_pr(
        self, owner: str, repo: str, branch: str, html: str,
        *, marker: str | None = None,
    ) -> None:
        """Find (or create) the PR and post/update the AI report comment."""
        comment_marker = marker or self.config.comment_marker
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
            owner, repo, pr_number, comment_marker,
        )
        if existing_id:
            self.client.update_comment(owner, repo, existing_id, html)
        else:
            self.client.create_comment(owner, repo, pr_number, html)

        log.info("AI report generation complete.")

    def _create_draft_pr(self, owner: str, repo: str, branch: str) -> int | None:
        """Create a draft PR via the GitHub REST API."""
        title = get_latest_commit_message() or branch

        if self.config.dry_run:
            log.info("[DRY-RUN] Would create draft PR '%s' on %s/%s.", title, owner, repo)
            return None

        try:
            pr_number = self.client.create_pr(
                owner,
                repo,
                head=branch,
                base=self.config.base_branch,
                title=title,
                body="Auto-generated PR created by SDLC automation.",
                draft=True,
            )
        except Exception as exc:
            err = str(exc)
            log.error("Failed to create draft PR: %s", err)
            if "'head'" in err and "invalid" in err:
                log.error(
                    "Hint: Branch '%s' may not exist on the remote. "
                    "Run 'git push -u origin %s' first.",
                    branch, branch,
                )
            elif "'base'" in err and "invalid" in err:
                log.error(
                    "Hint: Base branch '%s' may not exist. "
                    "Check your base_branch config.",
                    self.config.base_branch,
                )
            return None

        if pr_number is None:
            # POST may have been dry-run or returned error; try re-lookup
            existing = self.client.find_pr(owner, repo, branch)
            if existing:
                log.info("PR already exists (#%d).", existing)
            return existing

        return pr_number
