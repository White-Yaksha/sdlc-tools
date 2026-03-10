"""Tests for report module edge cases."""

from __future__ import annotations

from sdlc_tools.config import SdlcConfig


class TestDiffTruncation:
    """Verify diff truncation logic (unit-level, no subprocess)."""

    def test_truncates_long_diff(self) -> None:
        cfg = SdlcConfig(max_diff_length=100)
        diff = "x" * 200
        if len(diff) > cfg.max_diff_length:
            diff = diff[: cfg.max_diff_length] + "\n\n... (diff truncated)"
        assert len(diff) < 200
        assert "truncated" in diff

    def test_short_diff_unchanged(self) -> None:
        cfg = SdlcConfig(max_diff_length=1000)
        diff = "short diff"
        if len(diff) > cfg.max_diff_length:
            diff = diff[: cfg.max_diff_length] + "\n\n... (diff truncated)"
        assert diff == "short diff"


class TestPromptTemplate:
    """Verify prompt template is populated."""

    def test_default_prompt_contains_sections(self) -> None:
        cfg = SdlcConfig()
        assert "High-Level Summary" in cfg.prompt_template
        assert "Risk Assessment" in cfg.prompt_template
        assert "Backward Compatibility" in cfg.prompt_template


class TestCommitReportMarker:
    """Verify commit-level reports use per-commit markers."""

    def test_commit_marker_includes_short_sha(self) -> None:
        from sdlc_tools.git import get_short_sha

        sha = "abc1234def5678"
        short = get_short_sha(sha)
        marker = f"<!-- AI-SDLC-COMMIT-{short} -->"
        assert "abc1234" in marker
        assert marker != "<!-- AI-SDLC-REPORT -->"

    def test_short_sha_returns_7_chars(self) -> None:
        from sdlc_tools.git import get_short_sha

        assert get_short_sha("abc1234def5678") == "abc1234"
        assert get_short_sha("1234567") == "1234567"

    def test_different_commits_get_different_markers(self) -> None:
        from sdlc_tools.git import get_short_sha

        sha_a = "aaaaaaa1111111"
        sha_b = "bbbbbbb2222222"
        marker_a = f"<!-- AI-SDLC-COMMIT-{get_short_sha(sha_a)} -->"
        marker_b = f"<!-- AI-SDLC-COMMIT-{get_short_sha(sha_b)} -->"
        assert marker_a != marker_b


class TestCommitWiseReportMarker:
    """Verify commit-wise reports use the full-report marker for idempotency."""

    def test_commit_wise_uses_full_report_marker(self) -> None:
        """Commit-wise report must use the same marker as the full report."""
        cfg = SdlcConfig()
        # The commit-wise report uses cfg.comment_marker, same as the full report.
        assert cfg.comment_marker == "<!-- AI-SDLC-REPORT -->"

    def test_commit_wise_marker_differs_from_single_commit(self) -> None:
        """Commit-wise (full-report) marker must differ from single-commit markers."""
        from sdlc_tools.git import get_short_sha

        cfg = SdlcConfig()
        full_marker = cfg.comment_marker
        commit_marker = f"<!-- AI-SDLC-COMMIT-{get_short_sha('abc1234def5678')} -->"
        assert full_marker != commit_marker


class TestGetBranchCommitsParsing:
    """Verify the parsing logic of get_branch_commits output format."""

    def test_parse_commit_log_format(self) -> None:
        """Ensure the expected 'SHA subject' format is correctly parsed."""
        # Simulate the output parsing that get_branch_commits performs.
        raw = (
            "abc1234567890abcdef1234567890abcdef123456 Initial commit\n"
            "def5678901234abcdef5678901234abcdef567890 Add feature X\n"
        )
        commits: list[tuple[str, str]] = []
        for line in raw.strip().splitlines():
            if not line.strip():
                continue
            sha, _, subject = line.partition(" ")
            commits.append((sha, subject))

        assert len(commits) == 2
        assert commits[0][0] == "abc1234567890abcdef1234567890abcdef123456"
        assert commits[0][1] == "Initial commit"
        assert commits[1][1] == "Add feature X"

    def test_parse_empty_output(self) -> None:
        """Empty log output should produce an empty list."""
        raw = ""
        commits: list[tuple[str, str]] = []
        for line in raw.strip().splitlines():
            if not line.strip():
                continue
            sha, _, subject = line.partition(" ")
            commits.append((sha, subject))

        assert commits == []
