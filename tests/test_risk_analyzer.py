"""Tests for the rule-engine risk analyzer plugin."""

from __future__ import annotations

from pathlib import Path

import yaml

from sdlc_tools.analyzers.risk_analyzer import RiskAnalyzer


def _write_rules(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "high_risk_paths": ["migrations/", "auth/"],
        "file_type_rules": {
            ".sql": "database schema change",
            ".yaml": "config modification",
        },
        "dependency_files": ["requirements.txt", "package.json"],
        "patterns": [
            {"name": "schema_change", "regex": "ALTER TABLE|CREATE TABLE|DROP TABLE"},
            {"name": "retry_logic", "regex": "retry|backoff|timeout"},
        ],
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


class TestRiskAnalyzer:
    def test_emits_signals_and_file_summary(self, tmp_path: Path) -> None:
        rules = tmp_path / "config" / "risk_rules.yaml"
        _write_rules(rules)
        analyzer = RiskAnalyzer(str(rules))

        raw_diff = (
            "diff --git a/migrations/001.sql b/migrations/001.sql\n"
            "+++ b/migrations/001.sql\n"
            "+CREATE TABLE users(id INT);\n"
            "diff --git a/package.json b/package.json\n"
            "+++ b/package.json\n"
            "+{\"dependencies\": {\"x\": \"1.0.0\"}}\n"
            "diff --git a/config/app.yaml b/config/app.yaml\n"
            "+++ b/config/app.yaml\n"
            "+timeout: 30\n"
        )

        out = analyzer.analyze(raw_diff)

        assert "migrations/001.sql" in out["files"]
        assert "package.json" in out["files"]
        assert "config/app.yaml" in out["files"]
        assert "high-risk path change (migrations/)" in out["signals"]
        assert "database schema change" in out["signals"]
        assert "config modification" in out["signals"]
        assert "dependency update (package.json)" in out["signals"]
        assert "schema change" in out["signals"]
        assert "retry logic" in out["signals"]

    def test_missing_rule_file_still_returns_file_list(self, tmp_path: Path) -> None:
        analyzer = RiskAnalyzer(str(tmp_path / "missing.yaml"))
        raw_diff = "diff --git a/a.py b/a.py\n+++ b/a.py\n+print('x')\n"
        out = analyzer.analyze(raw_diff)
        assert out["files"] == ["a.py"]
        assert out["signals"] == []
