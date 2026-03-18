"""AI code impact report generation and PR comment posting."""

from __future__ import annotations

import re
import sys

from sdlc_tools.ai import get_provider
from sdlc_tools.analysis_pipeline import AnalysisPipeline
from sdlc_tools.client import GitHubClient
from sdlc_tools.config import SdlcConfig
from sdlc_tools.git import (
    get_branch_commits,
    get_current_branch,
    get_latest_commit_message,
    get_repo_url,
    get_short_sha,
)
from sdlc_tools.html import convert_markdown_to_html
from sdlc_tools.log import get_logger

log = get_logger("report")

_WRAPPER_PATTERNS: tuple[str, ...] = (
    r"(?im)^here is the structured markdown report:?\s*$",
    r"(?im)^here is the report in markdown format:?\s*$",
    r"(?im)^here is the markdown report:?\s*$",
)


def _normalize_ai_markdown(markdown: str) -> str:
    """Normalize provider output to a single clean Markdown report."""
    text = _unwrap_markdown_fence(markdown.strip())
    if not text:
        return ""

    for pattern in _WRAPPER_PATTERNS:
        matches = list(re.finditer(pattern, text))
        if matches:
            text = text[matches[-1].end():].lstrip()

    text = _drop_repeated_report_prefix(text)
    return text.strip()


def _unwrap_markdown_fence(text: str) -> str:
    match = re.match(r"^```(?:markdown|md)?\s*\n([\s\S]*?)\n```$", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


def _drop_repeated_report_prefix(text: str) -> str:
    """If report sections appear twice, keep only the last complete block."""
    pattern = re.compile(r"(?im)^\s*(?:#+\s*)?high-level summary\s*$")
    matches = list(pattern.finditer(text))
    if len(matches) < 2:
        return text

    cut = matches[-1].start()
    prefix = text[:cut].rstrip("\n")
    if prefix:
        line_start = prefix.rfind("\n") + 1
        title_line = prefix[line_start:].strip()
        if title_line and "report" in title_line.lower():
            cut = line_start
    return text[cut:].lstrip()


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

        pipeline = AnalysisPipeline(self.config)
        if commit_sha:
            short = get_short_sha(commit_sha)
            log.info("Commit mode: %s", short)
        diff = pipeline.fetch_diff(
            base_branch=self.config.base_branch,
            commit_sha=commit_sha,
        )

        if not diff or not diff.strip():
            log.info("No diff detected. Nothing to report.")
            return

        log.info("Diff length: %d characters.", len(diff))

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
            pipeline_output = pipeline.run(
                mode="report",
                provider=provider,
                diff=diff,
            )
            markdown_report = _normalize_ai_markdown(pipeline_output.markdown)
        except (RuntimeError, ValueError) as exc:
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

    def review(
        self,
        *,
        personas: list[str] | None = None,
        branch: str | None = None,
    ) -> None:
        """Generate reviewer feedback using review mode + optional personas.

        If *branch* is provided it overrides the current branch for both the
        diff computation and the PR lookup.  Review mode never pushes or
        creates PRs — if no open PR exists for the branch the review is
        skipped.
        """
        repo_full = self.config.github_repository or get_repo_url()
        if not repo_full or "/" not in repo_full:
            log.error("Could not determine repository (owner/repo).")
            sys.exit(1)

        owner, repo = repo_full.split("/", 1)
        branch = branch or get_current_branch()
        log.info("Branch: %s", branch)

        if branch == self.config.base_branch:
            log.info("On base branch '%s'. Nothing to review.", self.config.base_branch)
            return

        # Review mode requires an existing PR — never create one.
        pr_number = self.client.find_pr(owner, repo, branch)
        if pr_number is None:
            log.info(
                "No open PR found for branch '%s'. Skipping review.",
                branch,
            )
            return

        log.info("PR number: #%d", pr_number)

        pipeline = AnalysisPipeline(self.config)
        diff = pipeline.fetch_diff(
            base_branch=self.config.base_branch,
            head_ref=branch,
        )
        if not diff or not diff.strip():
            log.info("No diff detected. Nothing to review.")
            return

        try:
            provider = get_provider(self.config)
        except ValueError as exc:
            log.error("%s", exc)
            sys.exit(1)

        log.info("Using AI provider: %s", provider.name)

        if self.config.dry_run:
            log.info(
                "[DRY-RUN] Would invoke %s in review mode with %d-char diff.",
                provider.name, len(diff),
            )
            return

        try:
            pipeline_output = pipeline.run(
                mode="review",
                provider=provider,
                diff=diff,
                personas=personas or [],
            )
        except (RuntimeError, ValueError) as exc:
            log.error("AI review analysis failed: %s", exc)
            sys.exit(1)

        if not pipeline_output.markdown:
            log.warning("AI provider returned empty review response. Skipping review.")
            return

        normalized_review = _normalize_ai_markdown(pipeline_output.markdown)
        if not normalized_review:
            log.warning("AI provider returned empty review response after normalization.")
            return

        persona_label = ", ".join(pipeline_output.persona_names) or "none"
        html_report = convert_markdown_to_html(
            normalized_review,
            title="🔎 AI Code Review Report",
            marker=self.config.review_comment_marker,
            subtitle=f"Provider: {provider.display_name} | Personas: {persona_label}",
        )

        # Post or update comment on the existing PR.
        comment_marker = self.config.review_comment_marker
        existing_id = self.client.find_comment_by_marker(
            owner, repo, pr_number, comment_marker,
        )
        if existing_id:
            self.client.update_comment(owner, repo, existing_id, html_report)
        else:
            self.client.create_comment(owner, repo, pr_number, html_report)

        log.info("AI review generation complete.")

    # ------------------------------------------------------------------
    # PR interaction
    # ------------------------------------------------------------------

    def run_commit_wise(self) -> None:
        """Analyze each commit individually, combine into a single full report.

        Iterates over all commits between ``origin/<base_branch>`` and
        ``HEAD``, runs AI analysis on each commit's diff, then merges the
        per-commit Markdown sections into one HTML report posted with the
        standard full-report marker (``comment_marker``), making it
        idempotent against a regular ``run()`` full-report.
        """
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

        commits = get_branch_commits(self.config.base_branch)
        if not commits:
            log.info("No commits found between base and HEAD. Nothing to report.")
            return

        log.info("Found %d commit(s) to analyze.", len(commits))
        pipeline = AnalysisPipeline(self.config)

        try:
            provider = get_provider(self.config)
        except ValueError as exc:
            log.error("%s", exc)
            sys.exit(1)

        log.info("Using AI provider: %s", provider.name)
        markdown_sections: list[str] = []

        for idx, (sha, subject) in enumerate(commits, 1):
            short = get_short_sha(sha)
            log.info("[%d/%d] Analyzing commit %s: %s", idx, len(commits), short, subject)

            diff = pipeline.fetch_diff(
                base_branch=self.config.base_branch,
                commit_sha=sha,
            )
            if not diff or not diff.strip():
                log.info("  No diff for commit %s. Skipping.", short)
                continue

            if self.config.dry_run:
                log.info(
                    "[DRY-RUN] Would invoke %s for commit %s with %d-char diff.",
                    provider.name, short, len(diff),
                )
                continue

            try:
                pipeline_output = pipeline.run(
                    mode="report",
                    provider=provider,
                    diff=diff,
                )
                md = _normalize_ai_markdown(pipeline_output.markdown)
            except (RuntimeError, ValueError) as exc:
                log.error("AI analysis failed for commit %s: %s", short, exc)
                continue

            if not md:
                log.warning("AI returned empty response for commit %s. Skipping.", short)
                continue

            markdown_sections.append(
                f"## Commit `{short}` — {subject}\n\n{md}"
            )

        if self.config.dry_run:
            log.info("[DRY-RUN] Would post consolidated commit-wise report.")
            return

        if not markdown_sections:
            log.warning("No commit analyses produced. Skipping report.")
            return

        combined_markdown = "\n\n---\n\n".join(markdown_sections)
        provider_label = provider.display_name
        title = "\U0001f50d AI Code Impact Report (Commit-Wise)"
        marker = self.config.comment_marker
        subtitle = f"Provider: {provider_label} | Commits: {len(markdown_sections)}"

        html_report = convert_markdown_to_html(
            combined_markdown,
            title=title,
            marker=marker,
            subtitle=subtitle,
        )

        self._post_to_pr(owner, repo, branch, html_report, marker=marker)

    # ------------------------------------------------------------------
    # PR interaction (continued)
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
                body="Auto-generated PR created by [sdlc-tools](https://pypi.org/project/sdlc-tools/).",
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
