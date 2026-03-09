"""Tests for ReportGenerator orchestration."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from sdlc_tools.config import SdlcConfig
from sdlc_tools.report import ReportGenerator

_R = "sdlc_tools.report"


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


def _provider() -> MagicMock:
    p = MagicMock()
    p.name = "openai"
    p.display_name = "openai"
    return p


def _pipeline_output(markdown: str, personas: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        markdown=markdown,
        prompt="PROMPT",
        diff="DIFF",
        signals=[],
        files_changed=[],
        persona_names=personas or [],
    )


class TestRunReport:
    def test_full_report_posts_comment(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        provider = _provider()
        with (
            patch(f"{_R}.get_repo_url", return_value="owner/repo"),
            patch(f"{_R}.get_current_branch", return_value="feature/x"),
            patch(f"{_R}.get_provider", return_value=provider),
            patch(f"{_R}.convert_markdown_to_html", return_value="<html/>"),
            patch(f"{_R}.AnalysisPipeline") as pipeline_cls,
        ):
            pipeline = pipeline_cls.return_value
            pipeline.fetch_diff.return_value = "diff"
            pipeline.run.return_value = _pipeline_output("report")

            ReportGenerator(mock_client, report_config).run()

        pipeline.fetch_diff.assert_called_once_with(
            base_branch="main",
            commit_sha=None,
        )
        pipeline.run.assert_called_once()
        mock_client.find_pr.assert_called_once()

    def test_commit_report_uses_commit_marker(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        provider = _provider()
        with (
            patch(f"{_R}.get_repo_url", return_value="owner/repo"),
            patch(f"{_R}.get_current_branch", return_value="feature/x"),
            patch(f"{_R}.get_provider", return_value=provider),
            patch(f"{_R}.AnalysisPipeline") as pipeline_cls,
            patch(f"{_R}.convert_markdown_to_html", return_value="<html/>") as html,
        ):
            pipeline = pipeline_cls.return_value
            pipeline.fetch_diff.return_value = "diff"
            pipeline.run.return_value = _pipeline_output("report")
            ReportGenerator(mock_client, report_config).run(commit_sha="abc123456789")

        kwargs = html.call_args[1]
        assert "abc1234" in kwargs["marker"]
        assert "Commit Impact" in kwargs["title"]

    def test_skips_on_base_branch_without_commit(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        with (
            patch(f"{_R}.get_repo_url", return_value="owner/repo"),
            patch(f"{_R}.get_current_branch", return_value="main"),
        ):
            ReportGenerator(mock_client, report_config).run()
        mock_client.find_pr.assert_not_called()

    def test_skips_when_diff_empty(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        provider = _provider()
        with (
            patch(f"{_R}.get_repo_url", return_value="owner/repo"),
            patch(f"{_R}.get_current_branch", return_value="feature/x"),
            patch(f"{_R}.get_provider", return_value=provider),
            patch(f"{_R}.AnalysisPipeline") as pipeline_cls,
        ):
            pipeline = pipeline_cls.return_value
            pipeline.fetch_diff.return_value = ""
            ReportGenerator(mock_client, report_config).run()

        pipeline.run.assert_not_called()
        mock_client.find_pr.assert_not_called()

    def test_dry_run_skips_pipeline_run_and_post(
        self, mock_client: MagicMock, dry_run_config: SdlcConfig,
    ) -> None:
        provider = _provider()
        with (
            patch(f"{_R}.get_repo_url", return_value="owner/repo"),
            patch(f"{_R}.get_current_branch", return_value="feature/x"),
            patch(f"{_R}.get_provider", return_value=provider),
            patch(f"{_R}.AnalysisPipeline") as pipeline_cls,
        ):
            pipeline = pipeline_cls.return_value
            pipeline.fetch_diff.return_value = "diff"
            ReportGenerator(mock_client, dry_run_config).run()

        pipeline.run.assert_not_called()
        mock_client.find_pr.assert_not_called()

    def test_pipeline_failure_exits(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        provider = _provider()
        with (
            patch(f"{_R}.get_repo_url", return_value="owner/repo"),
            patch(f"{_R}.get_current_branch", return_value="feature/x"),
            patch(f"{_R}.get_provider", return_value=provider),
            patch(f"{_R}.AnalysisPipeline") as pipeline_cls,
            pytest.raises(SystemExit),
        ):
            pipeline = pipeline_cls.return_value
            pipeline.fetch_diff.return_value = "diff"
            pipeline.run.side_effect = ValueError("bad prompt config")
            ReportGenerator(mock_client, report_config).run()


class TestRunReview:
    def test_review_uses_review_mode_and_personas(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        provider = _provider()
        with (
            patch(f"{_R}.get_repo_url", return_value="owner/repo"),
            patch(f"{_R}.get_current_branch", return_value="feature/x"),
            patch(f"{_R}.get_provider", return_value=provider),
            patch(f"{_R}.AnalysisPipeline") as pipeline_cls,
            patch(f"{_R}.convert_markdown_to_html", return_value="<html/>") as html,
        ):
            pipeline = pipeline_cls.return_value
            pipeline.fetch_diff.return_value = "diff"
            pipeline.run.return_value = _pipeline_output(
                markdown="review markdown",
                personas=["security", "performance"],
            )
            ReportGenerator(mock_client, report_config).review(
                personas=["security", "performance"],
            )

        run_kwargs = pipeline.run.call_args.kwargs
        assert run_kwargs["mode"] == "review"
        assert run_kwargs["personas"] == ["security", "performance"]
        assert html.call_args[1]["marker"] == report_config.review_comment_marker

    def test_review_dry_run_skips_post(
        self, mock_client: MagicMock, dry_run_config: SdlcConfig,
    ) -> None:
        provider = _provider()
        with (
            patch(f"{_R}.get_repo_url", return_value="owner/repo"),
            patch(f"{_R}.get_current_branch", return_value="feature/x"),
            patch(f"{_R}.get_provider", return_value=provider),
            patch(f"{_R}.AnalysisPipeline") as pipeline_cls,
        ):
            pipeline = pipeline_cls.return_value
            pipeline.fetch_diff.return_value = "diff"
            ReportGenerator(mock_client, dry_run_config).review(personas=["security"])

        pipeline.run.assert_not_called()
        mock_client.find_pr.assert_not_called()


class TestRunCommitWise:
    def test_commit_wise_combines_reports(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        provider = _provider()
        commits = [("aaa1111", "First"), ("bbb2222", "Second")]
        with (
            patch(f"{_R}.get_repo_url", return_value="owner/repo"),
            patch(f"{_R}.get_current_branch", return_value="feature/x"),
            patch(f"{_R}.get_branch_commits", return_value=commits),
            patch(f"{_R}.get_provider", return_value=provider),
            patch(f"{_R}.AnalysisPipeline") as pipeline_cls,
            patch(f"{_R}.convert_markdown_to_html", return_value="<html/>") as html,
        ):
            pipeline = pipeline_cls.return_value
            pipeline.fetch_diff.side_effect = ["diff-a", "diff-b"]
            pipeline.run.side_effect = [
                _pipeline_output("md-a"),
                _pipeline_output("md-b"),
            ]
            ReportGenerator(mock_client, report_config).run_commit_wise()

        assert pipeline.run.call_count == 2
        combined_markdown = html.call_args[0][0]
        assert "Commit `aaa1111` — First" in combined_markdown
        assert "Commit `bbb2222` — Second" in combined_markdown

    def test_commit_wise_skips_empty_commit_diffs(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        provider = _provider()
        commits = [("aaa1111", "First"), ("bbb2222", "Second")]
        with (
            patch(f"{_R}.get_repo_url", return_value="owner/repo"),
            patch(f"{_R}.get_current_branch", return_value="feature/x"),
            patch(f"{_R}.get_branch_commits", return_value=commits),
            patch(f"{_R}.get_provider", return_value=provider),
            patch(f"{_R}.AnalysisPipeline") as pipeline_cls,
        ):
            pipeline = pipeline_cls.return_value
            pipeline.fetch_diff.side_effect = ["", "diff-b"]
            pipeline.run.return_value = _pipeline_output("md-b")
            ReportGenerator(mock_client, report_config).run_commit_wise()

        assert pipeline.run.call_count == 1


class TestPostToPr:
    def test_updates_existing_comment(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        mock_client.find_pr.return_value = 42
        mock_client.find_comment_by_marker.return_value = 999
        ReportGenerator(mock_client, report_config)._post_to_pr(
            "owner",
            "repo",
            "feat",
            "<html/>",
        )
        mock_client.update_comment.assert_called_once_with(
            "owner",
            "repo",
            999,
            "<html/>",
        )
        mock_client.create_comment.assert_not_called()

    def test_creates_new_comment(
        self, mock_client: MagicMock, report_config: SdlcConfig,
    ) -> None:
        mock_client.find_pr.return_value = 42
        mock_client.find_comment_by_marker.return_value = None
        ReportGenerator(mock_client, report_config)._post_to_pr(
            "owner",
            "repo",
            "feat",
            "<html/>",
        )
        mock_client.create_comment.assert_called_once_with("owner", "repo", 42, "<html/>")
