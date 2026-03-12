"""Shared analysis pipeline for report/review workflows."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sdlc_tools.analyzers.base_analyzer import BaseAnalyzer
from sdlc_tools.analyzers.risk_analyzer import RiskAnalyzer
from sdlc_tools.git import get_commit_diff, get_diff
from sdlc_tools.prompt_loader import PromptLoader

if TYPE_CHECKING:
    from sdlc_tools.ai import AIProvider
    from sdlc_tools.config import SdlcConfig


@dataclass
class AnalysisPipelineResult:
    """Result produced by pipeline execution."""

    markdown: str
    prompt: str
    diff: str
    signals: list[str]
    files_changed: list[str]
    persona_names: list[str]


class AnalysisPipeline:
    """Centralized pipeline for report/review analysis."""

    def __init__(
        self,
        config: SdlcConfig,
        *,
        analyzers: Sequence[BaseAnalyzer] | None = None,
        prompt_loader: PromptLoader | None = None,
    ) -> None:
        self.config = config
        self.analyzers = list(analyzers) if analyzers is not None else [
            RiskAnalyzer(config.risk_rules_file),
        ]
        self.prompt_loader = prompt_loader or PromptLoader(config)

    def fetch_diff(
        self,
        *,
        base_branch: str,
        commit_sha: str | None = None,
        head_ref: str = "HEAD",
    ) -> str:
        """Fetch a full branch diff or a single commit diff."""
        if commit_sha:
            return get_commit_diff(commit_sha)
        return get_diff(base_branch, head_ref=head_ref)

    def run(
        self,
        *,
        mode: str,
        provider: AIProvider,
        diff: str,
        personas: list[str] | None = None,
    ) -> AnalysisPipelineResult:
        """Run analyzers, build prompt from files, invoke provider, return result."""
        requested_personas = personas or []
        resolved_personas = self.prompt_loader.resolve_personas(mode, requested_personas)
        signals, files_changed = self._collect_signals(diff)
        prompt = self.prompt_loader.build_prompt(
            mode=mode,
            diff=diff,
            signals=signals,
            files_changed=files_changed,
            persona_names=resolved_personas,
        )
        markdown = provider.analyze(prompt, "")
        return AnalysisPipelineResult(
            markdown=markdown,
            prompt=prompt,
            diff=diff,
            signals=signals,
            files_changed=files_changed,
            persona_names=resolved_personas,
        )

    def _collect_signals(self, diff: str) -> tuple[list[str], list[str]]:
        signals: list[str] = []
        files: list[str] = []
        for analyzer in self.analyzers:
            output = analyzer.analyze(diff)
            signals.extend(_as_string_list(output.get("signals", [])))
            files.extend(_as_string_list(output.get("files", [])))
        return _unique(signals), _unique(files)


def _as_string_list(value: object) -> list[str]:
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
