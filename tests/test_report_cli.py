"""Tests for commit-level report CLI flags."""

from __future__ import annotations

from click.testing import CliRunner

from sdlc_tools.cli import main


class TestReportCommitFlags:
    """Verify --last-commit, --commit, and --commit-wise mutual exclusivity."""

    def test_last_commit_and_commit_exclusive(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["report", "--last-commit", "--commit", "abc1234"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower()

    def test_commit_wise_and_commit_exclusive(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["report", "--commit-wise", "--commit", "abc1234"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower()

    def test_commit_wise_and_last_commit_exclusive(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["report", "--commit-wise", "--last-commit"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower()

    def test_all_three_exclusive(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["report", "--commit-wise", "--last-commit", "--commit", "abc1234"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower()
