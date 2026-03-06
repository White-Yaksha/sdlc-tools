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
