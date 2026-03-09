"""Rule-engine analyzer for git diffs."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from sdlc_tools.analyzers.base_analyzer import BaseAnalyzer
from sdlc_tools.log import get_logger

log = get_logger("risk-analyzer")


class RiskAnalyzer(BaseAnalyzer):
    """Analyze git diffs against YAML-configured risk rules."""

    def __init__(self, rules_file: str = "config/risk_rules.yaml") -> None:
        self.rules_file = Path(rules_file)

    def analyze(self, diff: str) -> dict[str, list[str]]:
        """Return risk signals and file summary without mutating the diff."""
        rules = self._load_rules()
        changed_files = self._extract_changed_files(diff)
        signals: list[str] = []

        high_risk_paths = self._as_list(rules.get("high_risk_paths"))
        for path in changed_files:
            for prefix in high_risk_paths:
                if prefix and path.startswith(prefix):
                    signals.append(f"high-risk path change ({prefix})")
                    break

        file_type_rules = rules.get("file_type_rules", {})
        if isinstance(file_type_rules, dict):
            for ext, description in file_type_rules.items():
                ext_str = str(ext)
                if any(path.endswith(ext_str) for path in changed_files):
                    signals.append(str(description))

        dependency_files = self._as_list(rules.get("dependency_files"))
        for dep in dependency_files:
            if any(path == dep or path.endswith(f"/{dep}") for path in changed_files):
                signals.append(f"dependency update ({dep})")

        patterns = rules.get("patterns", [])
        if isinstance(patterns, list):
            for pattern in patterns:
                if not isinstance(pattern, dict):
                    continue
                regex = str(pattern.get("regex", "")).strip()
                if not regex:
                    continue
                label = str(pattern.get("name", "pattern_match")).replace("_", " ")
                if re.search(regex, diff, flags=re.IGNORECASE | re.MULTILINE):
                    signals.append(label)

        return {
            "signals": _unique(signals),
            "files": _unique(changed_files),
        }

    def _load_rules(self) -> dict:
        if not self.rules_file.is_file():
            log.warning("Risk rule file not found: %s", self.rules_file)
            return {}
        try:
            with open(self.rules_file, encoding="utf-8") as fh:
                raw = yaml.safe_load(fh)
        except (OSError, yaml.YAMLError) as exc:
            raise ValueError(f"Failed to load risk rules from {self.rules_file}: {exc}") from exc
        return raw if isinstance(raw, dict) else {}

    @staticmethod
    def _extract_changed_files(diff: str) -> list[str]:
        files: list[str] = []
        for line in diff.splitlines():
            if not line.startswith("diff --git "):
                continue
            match = re.match(r"^diff --git a/(.+?) b/(.+)$", line)
            if not match:
                continue
            old_path, new_path = match.groups()
            candidate = new_path if new_path != "/dev/null" else old_path
            files.append(candidate)
        return _unique(files)

    @staticmethod
    def _as_list(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        return []


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered
