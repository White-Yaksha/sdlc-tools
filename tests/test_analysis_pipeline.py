"""Tests for shared analysis pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import yaml

from sdlc_tools.analysis_pipeline import AnalysisPipeline
from sdlc_tools.analyzers.base_analyzer import BaseAnalyzer
from sdlc_tools.config import SdlcConfig


class _DummyAnalyzer(BaseAnalyzer):
    def analyze(self, diff: str) -> dict[str, list[str]]:
        assert "diff --git" in diff
        return {
            "signals": ["dummy-signal"],
            "files": ["src/main.py"],
        }


class _DummyProvider:
    name = "dummy"
    display_name = "dummy"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def analyze(self, prompt: str, diff: str) -> str:
        self.calls.append((prompt, diff))
        return "MARKDOWN"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _config(tmp_path: Path) -> SdlcConfig:
    instructions = tmp_path / "instructions"
    personas_cfg = tmp_path / "config" / "review_personas.yaml"
    rules_file = tmp_path / "config" / "risk_rules.yaml"

    _write(instructions / "report" / "report_base.md", "REPORT BASE")
    _write(instructions / "review" / "review_base.md", "REVIEW BASE")
    sec = instructions / "review" / "personas" / "security.md"
    arch = instructions / "review" / "personas" / "architecture.md"
    _write(sec, "SECURITY")
    _write(arch, "ARCH")
    _write(rules_file, "high_risk_paths: []\n")
    _write(
        personas_cfg,
        yaml.safe_dump(
            {
                "primary_persona": "security",
                "personas": {
                    "security": str(sec),
                    "architecture": str(arch),
                },
            },
            sort_keys=False,
        ),
    )
    return SdlcConfig(
        instruction_root=str(instructions),
        review_personas_file=str(personas_cfg),
        risk_rules_file=str(rules_file),
    )


class TestAnalysisPipeline:
    def test_fetch_diff_uses_git_helpers(self, tmp_path: Path) -> None:
        cfg = _config(tmp_path)
        pipeline = AnalysisPipeline(cfg, analyzers=[_DummyAnalyzer()])

        with patch("sdlc_tools.analysis_pipeline.get_diff", return_value="FULL") as full:
            assert pipeline.fetch_diff(base_branch="main") == "FULL"
            full.assert_called_once_with("main")

        with patch(
            "sdlc_tools.analysis_pipeline.get_commit_diff",
            return_value="COMMIT",
        ) as commit:
            assert pipeline.fetch_diff(base_branch="main", commit_sha="abc") == "COMMIT"
            commit.assert_called_once_with("abc")

    def test_run_report_mode_builds_prompt_and_calls_provider(
        self, tmp_path: Path,
    ) -> None:
        cfg = _config(tmp_path)
        provider = _DummyProvider()
        pipeline = AnalysisPipeline(cfg, analyzers=[_DummyAnalyzer()])

        diff = "diff --git a/src/main.py b/src/main.py\n+print('x')\n"
        out = pipeline.run(mode="report", provider=provider, diff=diff)

        assert out.markdown == "MARKDOWN"
        assert out.signals == ["dummy-signal"]
        assert out.files_changed == ["src/main.py"]
        assert out.persona_names == []
        assert provider.calls[0][1] == ""
        assert "REPORT BASE" in provider.calls[0][0]
        assert provider.calls[0][0].endswith("Git Diff\n" + diff)

    def test_run_review_mode_uses_primary_persona(self, tmp_path: Path) -> None:
        cfg = _config(tmp_path)
        provider = _DummyProvider()
        pipeline = AnalysisPipeline(cfg, analyzers=[_DummyAnalyzer()])

        diff = "diff --git a/src/main.py b/src/main.py\n+print('x')\n"
        out = pipeline.run(mode="review", provider=provider, diff=diff, personas=[])

        assert out.persona_names == ["security"]
        prompt = provider.calls[0][0]
        assert "REVIEW BASE" in prompt
        assert "SECURITY" in prompt

    def test_run_review_mode_all_personas(self, tmp_path: Path) -> None:
        cfg = _config(tmp_path)
        provider = _DummyProvider()
        pipeline = AnalysisPipeline(cfg, analyzers=[_DummyAnalyzer()])

        diff = "diff --git a/src/main.py b/src/main.py\n+print('x')\n"
        out = pipeline.run(mode="review", provider=provider, diff=diff, personas=["all"])

        assert out.persona_names == ["architecture", "security"]
        prompt = provider.calls[0][0]
        assert "SECURITY" in prompt
        assert "ARCH" in prompt
