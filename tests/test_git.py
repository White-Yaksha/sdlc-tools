"""Tests for git module — subprocess-based helpers with mocked git commands."""

from __future__ import annotations

import subprocess as _subprocess
from unittest.mock import MagicMock, patch

import pytest

from sdlc_tools.git import (
    fetch_branch,
    get_branch_commits,
    get_commit_diff,
    get_current_branch,
    get_diff,
    get_last_commit_sha,
    get_latest_commit_message,
    get_repo_url,
    get_short_sha,
    push_current_branch,
)

_GIT_RUN = "sdlc_tools.git.subprocess.run"
_GIT_FETCH = "sdlc_tools.git.fetch_branch"
_GIT_BRANCH = "sdlc_tools.git.get_current_branch"


def _mock_run(
    stdout: str = "", stderr: str = "", returncode: int = 0,
) -> MagicMock:
    """Create a mock subprocess result."""
    m = MagicMock()
    m.stdout = stdout
    m.stderr = stderr
    m.returncode = returncode
    return m


_FAIL = _mock_run(returncode=1, stderr="err")


class TestGetCurrentBranch:
    def test_returns_branch_name(self) -> None:
        with patch(_GIT_RUN, return_value=_mock_run("feature/foo\n")):
            assert get_current_branch() == "feature/foo"

    def test_exits_on_failure(self) -> None:
        with (
            patch(_GIT_RUN, return_value=_FAIL),
            pytest.raises(SystemExit),
        ):
            get_current_branch()


class TestGetDiff:
    def test_returns_diff(self) -> None:
        with (
            patch(_GIT_RUN, return_value=_mock_run("diff output")),
            patch(_GIT_FETCH),
        ):
            result = get_diff("main")
        assert result == "diff output"

    def test_exits_on_failure(self) -> None:
        fail = _mock_run(returncode=1, stderr="error")
        with (
            patch(_GIT_FETCH),
            patch(_GIT_RUN, return_value=fail),
            pytest.raises(SystemExit),
        ):
            get_diff("main")


class TestFetchBranch:
    def test_success(self) -> None:
        with patch(_GIT_RUN, return_value=_mock_run()):
            fetch_branch("main")

    def test_warns_on_failure(self) -> None:
        with patch(_GIT_RUN, return_value=_FAIL):
            fetch_branch("main")  # Should not raise


class TestGetRepoUrl:
    def test_parses_https(self) -> None:
        url = "https://github.com/owner/repo.git\n"
        with patch(_GIT_RUN, return_value=_mock_run(url)):
            assert get_repo_url() == "owner/repo"

    def test_parses_ssh(self) -> None:
        url = "git@github.com:owner/repo.git\n"
        with patch(_GIT_RUN, return_value=_mock_run(url)):
            assert get_repo_url() == "owner/repo"

    def test_fallback_to_env(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("GITHUB_REPOSITORY", "env-owner/env-repo")
        with patch(_GIT_RUN, side_effect=FileNotFoundError):
            assert get_repo_url() == "env-owner/env-repo"


class TestGetLatestCommitMessage:
    def test_returns_subject(self) -> None:
        with patch(_GIT_RUN, return_value=_mock_run("fix: stuff\n")):
            assert get_latest_commit_message() == "fix: stuff"

    def test_returns_empty_on_failure(self) -> None:
        with patch(_GIT_RUN, return_value=_mock_run(returncode=1)):
            assert get_latest_commit_message() == ""

    def test_returns_empty_on_timeout(self) -> None:
        err = _subprocess.TimeoutExpired("git", 30)
        with patch(_GIT_RUN, side_effect=err):
            assert get_latest_commit_message() == ""


class TestPushCurrentBranch:
    def test_success(self) -> None:
        with (
            patch(_GIT_BRANCH, return_value="feat"),
            patch(_GIT_RUN, return_value=_mock_run()),
        ):
            assert push_current_branch() is True

    def test_failure(self) -> None:
        with (
            patch(_GIT_BRANCH, return_value="feat"),
            patch(_GIT_RUN, return_value=_FAIL),
        ):
            assert push_current_branch() is False

    def test_force_flag(self) -> None:
        with (
            patch(_GIT_BRANCH, return_value="feat"),
            patch(_GIT_RUN, return_value=_mock_run()) as mock,
        ):
            push_current_branch(force=True)
            cmd = mock.call_args[0][0]
            assert "--force" in cmd


class TestGetLastCommitSha:
    def test_returns_sha(self) -> None:
        sha = "abc123def456"
        with patch(_GIT_RUN, return_value=_mock_run(sha + "\n")):
            assert get_last_commit_sha() == sha

    def test_exits_on_failure(self) -> None:
        with (
            patch(_GIT_RUN, return_value=_FAIL),
            pytest.raises(SystemExit),
        ):
            get_last_commit_sha()


class TestGetCommitDiff:
    def test_returns_diff(self) -> None:
        with patch(_GIT_RUN, return_value=_mock_run("commit diff")):
            assert get_commit_diff("abc123") == "commit diff"

    def test_exits_on_failure(self) -> None:
        with (
            patch(_GIT_RUN, return_value=_FAIL),
            pytest.raises(SystemExit),
        ):
            get_commit_diff("abc123")


class TestGetBranchCommits:
    def test_returns_parsed_commits(self) -> None:
        stdout = (
            "abc1234567890abcdef1234567890abcdef123456 "
            "Initial commit\n"
            "def5678901234abcdef5678901234abcdef567890 "
            "Add feature X\n"
        )
        with (
            patch(_GIT_FETCH),
            patch(_GIT_RUN, return_value=_mock_run(stdout)),
        ):
            commits = get_branch_commits("main")

        assert len(commits) == 2
        assert commits[0][1] == "Initial commit"
        assert commits[1][1] == "Add feature X"

    def test_returns_empty_for_no_commits(self) -> None:
        with (
            patch(_GIT_FETCH),
            patch(_GIT_RUN, return_value=_mock_run("")),
        ):
            commits = get_branch_commits("main")
        assert commits == []

    def test_exits_on_failure(self) -> None:
        fail = _mock_run(returncode=1, stderr="bad revision")
        with (
            patch(_GIT_FETCH),
            patch(_GIT_RUN, return_value=fail),
            pytest.raises(SystemExit),
        ):
            get_branch_commits("main")

    def test_calls_fetch_branch_first(self) -> None:
        with (
            patch(_GIT_FETCH) as mock_fetch,
            patch(_GIT_RUN, return_value=_mock_run("")),
        ):
            get_branch_commits("develop")
        mock_fetch.assert_called_once_with("develop")

    def test_handles_subjects_with_spaces(self) -> None:
        stdout = (
            "abc1234567890abcdef1234567890abcdef123456 "
            "fix: handle edge case in parser\n"
        )
        with (
            patch(_GIT_FETCH),
            patch(_GIT_RUN, return_value=_mock_run(stdout)),
        ):
            commits = get_branch_commits("main")
        assert commits[0][1] == "fix: handle edge case in parser"


class TestGetShortSha:
    def test_truncates_to_7(self) -> None:
        assert get_short_sha("abc1234def5678") == "abc1234"

    def test_short_input(self) -> None:
        assert get_short_sha("abc") == "abc"
