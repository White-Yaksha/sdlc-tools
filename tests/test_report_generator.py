"""Tests for ReportGenerator — mocked subprocess, AI, and GitHub client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sdlc_tools.config import SdlcConfig
from sdlc_tools.report import ReportGenerator

_P = "sdlc_tools.report"
_HTML = f"{_P}.convert_markdown_to_html"


@pytest.fixture()
def mock_client() -> MagicMock:
    client = MagicMock()
    client.dry_run = False
    client.find_pr.return_value = 42
    client.find_comment_by_marker.return_value = None
    return client


@pytest.fixture()
def report_config() -> SdlcConfig:
    return SdlcConfig(
        github_token="test-token",
        github_repository="owner/repo",
        base_branch="main",
        ai_provider="openai",
        ai_api_key="sk-test",
        dry_run=False,
    )


@pytest.fixture()
def dry_run_config() -> SdlcConfig:
    return SdlcConfig(
        github_token="test-token",
        github_repository="owner/repo",
        base_branch="main",
        ai_provider="openai",
        ai_api_key="sk-test",
        dry_run=True,
    )


def _provider(
    analyze_rv: str | list | Exception = "report",
) -> MagicMock:
    """Create a mock AI provider."""
    p = MagicMock()
    p.name = "openai"
    p.display_name = "openai"
    if isinstance(analyze_rv, (list, Exception)):
        p.analyze.side_effect = analyze_rv
    else:
        p.analyze.return_value = analyze_rv
    return p


# ------------------------------------------------------------------
# run() — full branch diff mode
# ------------------------------------------------------------------


class TestRunFullReport:
    def test_generates_and_posts_report(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        prov = _provider("## Summary\nLooks good.")
        with (
            patch(f"{_P}.get_repo_url", return_value="owner/repo"),
            patch(f"{_P}.get_current_branch", return_value="feat/x"),
            patch(f"{_P}.get_diff", return_value="diff content"),
            patch(f"{_P}.get_provider", return_value=prov),
            patch(_HTML, return_value="<html>r</html>"),
        ):
            ReportGenerator(mock_client, report_config).run()

        prov.analyze.assert_called_once()
        mock_client.find_pr.assert_called_once()

    def test_skips_on_base_branch(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        with (
            patch(f"{_P}.get_repo_url", return_value="owner/repo"),
            patch(f"{_P}.get_current_branch", return_value="main"),
        ):
            ReportGenerator(mock_client, report_config).run()

        mock_client.find_pr.assert_not_called()

    def test_skips_empty_diff(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        with (
            patch(f"{_P}.get_repo_url", return_value="owner/repo"),
            patch(f"{_P}.get_current_branch", return_value="feat"),
            patch(f"{_P}.get_diff", return_value=""),
        ):
            ReportGenerator(mock_client, report_config).run()

        mock_client.find_pr.assert_not_called()

    def test_truncates_long_diff(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        report_config.max_diff_length = 50
        prov = _provider()

        with (
            patch(f"{_P}.get_repo_url", return_value="owner/repo"),
            patch(f"{_P}.get_current_branch", return_value="feat"),
            patch(f"{_P}.get_diff", return_value="x" * 200),
            patch(f"{_P}.get_provider", return_value=prov),
            patch(_HTML, return_value="<html/>"),
        ):
            ReportGenerator(mock_client, report_config).run()

        passed_diff = prov.analyze.call_args[0][1]
        assert len(passed_diff) < 200
        assert "truncated" in passed_diff

    def test_dry_run_skips_ai(
        self, mock_client: MagicMock, dry_run_config: SdlcConfig,
    ) -> None:
        prov = _provider()

        with (
            patch(f"{_P}.get_repo_url", return_value="owner/repo"),
            patch(f"{_P}.get_current_branch", return_value="feat"),
            patch(f"{_P}.get_diff", return_value="diff"),
            patch(f"{_P}.get_provider", return_value=prov),
        ):
            ReportGenerator(mock_client, dry_run_config).run()

        prov.analyze.assert_not_called()

    def test_exits_on_bad_repo(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        report_config.github_repository = ""
        with (
            patch(f"{_P}.get_repo_url", return_value=""),
            pytest.raises(SystemExit),
        ):
            ReportGenerator(mock_client, report_config).run()

    def test_empty_ai_response_skips_post(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        prov = _provider("")

        with (
            patch(f"{_P}.get_repo_url", return_value="owner/repo"),
            patch(f"{_P}.get_current_branch", return_value="feat"),
            patch(f"{_P}.get_diff", return_value="diff"),
            patch(f"{_P}.get_provider", return_value=prov),
        ):
            ReportGenerator(mock_client, report_config).run()

        mock_client.find_pr.assert_not_called()

    def test_ai_error_exits(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        prov = _provider(RuntimeError("API down"))

        with (
            patch(f"{_P}.get_repo_url", return_value="owner/repo"),
            patch(f"{_P}.get_current_branch", return_value="feat"),
            patch(f"{_P}.get_diff", return_value="diff"),
            patch(f"{_P}.get_provider", return_value=prov),
            pytest.raises(SystemExit),
        ):
            ReportGenerator(mock_client, report_config).run()

    def test_provider_error_exits(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        with (
            patch(f"{_P}.get_repo_url", return_value="owner/repo"),
            patch(f"{_P}.get_current_branch", return_value="feat"),
            patch(f"{_P}.get_diff", return_value="diff"),
            patch(f"{_P}.get_provider", side_effect=ValueError("bad")),
            pytest.raises(SystemExit),
        ):
            ReportGenerator(mock_client, report_config).run()


# ------------------------------------------------------------------
# run(commit_sha=...) — single commit mode
# ------------------------------------------------------------------


class TestRunCommitMode:
    def test_single_commit_uses_commit_marker(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        prov = _provider()

        with (
            patch(f"{_P}.get_repo_url", return_value="owner/repo"),
            patch(f"{_P}.get_current_branch", return_value="feat"),
            patch(f"{_P}.get_commit_diff", return_value="cdiff"),
            patch(f"{_P}.get_provider", return_value=prov),
            patch(_HTML, return_value="<html/>") as mhtml,
        ):
            gen = ReportGenerator(mock_client, report_config)
            gen.run(commit_sha="abc1234567890")

        kw = mhtml.call_args[1]
        assert "abc1234" in kw["marker"]
        assert "Commit Impact" in kw["title"]

    def test_commit_mode_skips_base_branch_check(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        """Commit mode should work even on the base branch."""
        prov = _provider()

        with (
            patch(f"{_P}.get_repo_url", return_value="owner/repo"),
            patch(f"{_P}.get_current_branch", return_value="main"),
            patch(f"{_P}.get_commit_diff", return_value="diff"),
            patch(f"{_P}.get_provider", return_value=prov),
            patch(_HTML, return_value="<html/>"),
        ):
            gen = ReportGenerator(mock_client, report_config)
            gen.run(commit_sha="abc1234567890")

        prov.analyze.assert_called_once()


# ------------------------------------------------------------------
# run_commit_wise() — per-commit consolidated report
# ------------------------------------------------------------------


class TestRunCommitWise:
    def test_analyzes_all_commits(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        prov = _provider(["Analysis 1", "Analysis 2"])
        commits = [("aaa1111", "First"), ("bbb2222", "Second")]

        with (
            patch(f"{_P}.get_repo_url", return_value="owner/repo"),
            patch(f"{_P}.get_current_branch", return_value="feat"),
            patch(f"{_P}.get_branch_commits", return_value=commits),
            patch(f"{_P}.get_commit_diff", return_value="diff"),
            patch(f"{_P}.get_provider", return_value=prov),
            patch(_HTML, return_value="<html/>") as mhtml,
        ):
            ReportGenerator(mock_client, report_config).run_commit_wise()

        assert prov.analyze.call_count == 2
        mhtml.assert_called_once()
        kw = mhtml.call_args[1]
        assert kw["marker"] == report_config.comment_marker

    def test_uses_full_report_marker(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        """Commit-wise report must be idempotent against full report."""
        prov = _provider("Analysis")

        with (
            patch(f"{_P}.get_repo_url", return_value="owner/repo"),
            patch(f"{_P}.get_current_branch", return_value="feat"),
            patch(f"{_P}.get_branch_commits", return_value=[("a", "m")]),
            patch(f"{_P}.get_commit_diff", return_value="diff"),
            patch(f"{_P}.get_provider", return_value=prov),
            patch(_HTML, return_value="<html/>") as mhtml,
        ):
            ReportGenerator(mock_client, report_config).run_commit_wise()

        marker = mhtml.call_args[1]["marker"]
        assert marker == "<!-- AI-SDLC-REPORT -->"

    def test_skips_on_base_branch(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        with (
            patch(f"{_P}.get_repo_url", return_value="owner/repo"),
            patch(f"{_P}.get_current_branch", return_value="main"),
        ):
            ReportGenerator(mock_client, report_config).run_commit_wise()

        mock_client.find_pr.assert_not_called()

    def test_skips_empty_commit_diff(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        prov = _provider()

        with (
            patch(f"{_P}.get_repo_url", return_value="owner/repo"),
            patch(f"{_P}.get_current_branch", return_value="feat"),
            patch(f"{_P}.get_branch_commits", return_value=[("a", "e")]),
            patch(f"{_P}.get_commit_diff", return_value=""),
            patch(f"{_P}.get_provider", return_value=prov),
        ):
            ReportGenerator(mock_client, report_config).run_commit_wise()

        prov.analyze.assert_not_called()

    def test_handles_ai_error_gracefully(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        prov = _provider([RuntimeError("fail"), "OK report"])
        commits = [("aaa", "Bad"), ("bbb", "Good")]

        with (
            patch(f"{_P}.get_repo_url", return_value="owner/repo"),
            patch(f"{_P}.get_current_branch", return_value="feat"),
            patch(f"{_P}.get_branch_commits", return_value=commits),
            patch(f"{_P}.get_commit_diff", return_value="diff"),
            patch(f"{_P}.get_provider", return_value=prov),
            patch(_HTML, return_value="<html/>") as mhtml,
        ):
            ReportGenerator(mock_client, report_config).run_commit_wise()

        combined = mhtml.call_args[0][0]
        assert "Good" in combined
        assert "Bad" not in combined

    def test_no_commits_skips_report(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        with (
            patch(f"{_P}.get_repo_url", return_value="owner/repo"),
            patch(f"{_P}.get_current_branch", return_value="feat"),
            patch(f"{_P}.get_branch_commits", return_value=[]),
        ):
            ReportGenerator(mock_client, report_config).run_commit_wise()

        mock_client.find_pr.assert_not_called()

    def test_dry_run_skips_ai_and_post(
        self, mock_client: MagicMock, dry_run_config: SdlcConfig,
    ) -> None:
        prov = _provider()

        with (
            patch(f"{_P}.get_repo_url", return_value="owner/repo"),
            patch(f"{_P}.get_current_branch", return_value="feat"),
            patch(f"{_P}.get_branch_commits", return_value=[("a", "m")]),
            patch(f"{_P}.get_commit_diff", return_value="diff"),
            patch(f"{_P}.get_provider", return_value=prov),
        ):
            ReportGenerator(mock_client, dry_run_config).run_commit_wise()

        prov.analyze.assert_not_called()
        mock_client.find_pr.assert_not_called()

    def test_truncates_long_commit_diff(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        report_config.max_diff_length = 50
        prov = _provider()

        with (
            patch(f"{_P}.get_repo_url", return_value="owner/repo"),
            patch(f"{_P}.get_current_branch", return_value="feat"),
            patch(f"{_P}.get_branch_commits", return_value=[("a", "m")]),
            patch(f"{_P}.get_commit_diff", return_value="x" * 200),
            patch(f"{_P}.get_provider", return_value=prov),
            patch(_HTML, return_value="<html/>"),
        ):
            ReportGenerator(mock_client, report_config).run_commit_wise()

        passed_diff = prov.analyze.call_args[0][1]
        assert "truncated" in passed_diff

    def test_exits_on_bad_repo(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        report_config.github_repository = ""
        with (
            patch(f"{_P}.get_repo_url", return_value=""),
            pytest.raises(SystemExit),
        ):
            ReportGenerator(mock_client, report_config).run_commit_wise()

    def test_provider_error_exits(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        with (
            patch(f"{_P}.get_repo_url", return_value="owner/repo"),
            patch(f"{_P}.get_current_branch", return_value="feat"),
            patch(f"{_P}.get_branch_commits", return_value=[("a", "m")]),
            patch(f"{_P}.get_commit_diff", return_value="diff"),
            patch(f"{_P}.get_provider", side_effect=ValueError("bad")),
            pytest.raises(SystemExit),
        ):
            ReportGenerator(mock_client, report_config).run_commit_wise()

    def test_empty_ai_response_skipped(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        prov = _provider("")

        with (
            patch(f"{_P}.get_repo_url", return_value="owner/repo"),
            patch(f"{_P}.get_current_branch", return_value="feat"),
            patch(f"{_P}.get_branch_commits", return_value=[("a", "m")]),
            patch(f"{_P}.get_commit_diff", return_value="diff"),
            patch(f"{_P}.get_provider", return_value=prov),
        ):
            ReportGenerator(mock_client, report_config).run_commit_wise()

        mock_client.find_pr.assert_not_called()


# ------------------------------------------------------------------
# _post_to_pr — PR comment posting
# ------------------------------------------------------------------


class TestPostToPr:
    def test_updates_existing_comment(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        mock_client.find_pr.return_value = 42
        mock_client.find_comment_by_marker.return_value = 999

        gen = ReportGenerator(mock_client, report_config)
        gen._post_to_pr("owner", "repo", "feat", "<html/>")

        mock_client.update_comment.assert_called_once_with(
            "owner", "repo", 999, "<html/>",
        )
        mock_client.create_comment.assert_not_called()

    def test_creates_new_comment(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        mock_client.find_pr.return_value = 42
        mock_client.find_comment_by_marker.return_value = None

        gen = ReportGenerator(mock_client, report_config)
        gen._post_to_pr("owner", "repo", "feat", "<html/>")

        mock_client.create_comment.assert_called_once_with(
            "owner", "repo", 42, "<html/>",
        )

    def test_creates_draft_pr_when_missing(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        mock_client.find_pr.return_value = None
        mock_client.create_pr.return_value = 99
        mock_client.find_comment_by_marker.return_value = None

        msg_patch = f"{_P}.get_latest_commit_message"
        with patch(msg_patch, return_value="feat: new"):
            gen = ReportGenerator(mock_client, report_config)
            gen._post_to_pr("owner", "repo", "feat", "<html/>")

        mock_client.create_pr.assert_called_once()
        mock_client.create_comment.assert_called_once()

    def test_skips_post_when_pr_create_fails(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        mock_client.find_pr.side_effect = [None, None]
        mock_client.create_pr.return_value = None

        msg_patch = f"{_P}.get_latest_commit_message"
        with patch(msg_patch, return_value="msg"):
            gen = ReportGenerator(mock_client, report_config)
            gen._post_to_pr("owner", "repo", "feat", "<html/>")

        mock_client.create_comment.assert_not_called()
