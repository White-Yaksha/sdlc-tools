"""Tests for instruction-file prompt loading."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sdlc_tools.config import SdlcConfig
from sdlc_tools.prompt_loader import PromptLoader


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_loader(tmp_path: Path) -> PromptLoader:
    instr_root = tmp_path / "instructions"
    config_path = tmp_path / "config" / "review_personas.yaml"
    security = tmp_path / "instructions" / "review" / "personas" / "security.md"
    performance = tmp_path / "instructions" / "review" / "personas" / "performance.md"

    _write(instr_root / "report" / "report_base.md", "REPORT BASE")
    _write(instr_root / "review" / "review_base.md", "REVIEW BASE")
    _write(security, "SECURITY PERSONA")
    _write(performance, "PERFORMANCE PERSONA")

    data = {
        "primary_persona": "security",
        "personas": {
            "security": str(security),
            "performance": str(performance),
        },
    }
    _write(config_path, yaml.safe_dump(data, sort_keys=False))

    cfg = SdlcConfig(
        instruction_root=str(instr_root),
        review_personas_file=str(config_path),
    )
    return PromptLoader(cfg)


class TestPromptLoader:
    def test_load_report_base_instruction(self, tmp_path: Path) -> None:
        loader = _build_loader(tmp_path)
        assert loader.load_base_instruction("report") == "REPORT BASE"

    def test_resolve_primary_persona_when_omitted(self, tmp_path: Path) -> None:
        loader = _build_loader(tmp_path)
        assert loader.resolve_personas("review", []) == ["security"]

    def test_resolve_all_personas(self, tmp_path: Path) -> None:
        loader = _build_loader(tmp_path)
        assert loader.resolve_personas("review", ["all"]) == [
            "performance",
            "security",
        ]

    def test_unknown_persona_raises(self, tmp_path: Path) -> None:
        loader = _build_loader(tmp_path)
        with pytest.raises(ValueError, match="Unknown persona"):
            loader.resolve_personas("review", ["nonexistent"])

    def test_build_prompt_contains_signals_files_and_raw_diff(
        self, tmp_path: Path,
    ) -> None:
        loader = _build_loader(tmp_path)
        raw_diff = "diff --git a/a.py b/a.py\n+print('hello')\n"
        prompt = loader.build_prompt(
            mode="review",
            diff=raw_diff,
            signals=["dependency update"],
            files_changed=["a.py"],
            persona_names=["security"],
        )

        assert "REVIEW BASE" in prompt
        assert "SECURITY PERSONA" in prompt
        assert "Risk Signals" in prompt
        assert "Files Changed" in prompt
        assert prompt.endswith("Git Diff\n" + raw_diff)
