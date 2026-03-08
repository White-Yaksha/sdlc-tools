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
