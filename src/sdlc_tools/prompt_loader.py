"""Instruction-file prompt loading and construction."""

from __future__ import annotations

from pathlib import Path

import yaml

from sdlc_tools.config import SdlcConfig
from sdlc_tools.log import get_logger

log = get_logger("prompt-loader")


class PromptLoader:
    """Load base/persona instructions and build model prompts."""

    def __init__(self, config: SdlcConfig) -> None:
        self.config = config
        self.instruction_root = Path(config.instruction_root)
        self.review_personas_file = Path(config.review_personas_file)

    def load_base_instruction(self, mode: str) -> str:
        """Load report/review base instruction from markdown files."""
        if mode == "report":
            path = self.instruction_root / "report" / "report_base.md"
        elif mode == "review":
            path = self.instruction_root / "review" / "review_base.md"
        else:
            raise ValueError(f"Unknown mode '{mode}'. Expected 'report' or 'review'.")

        if path.is_file():
            return path.read_text(encoding="utf-8")

        if self.config.prompt_template:
            log.warning(
                "Instruction file '%s' not found; falling back to configured prompt template.",
                path,
            )
            return self.config.prompt_template

        raise ValueError(f"Instruction file not found: {path}")

    def resolve_personas(self, mode: str, requested: list[str]) -> list[str]:
        """Resolve persona names based on requested options and config."""
        if mode != "review":
            return []

        config = self._load_persona_config(required=True)
        personas = config.get("personas", {})
        if not isinstance(personas, dict) or not personas:
            raise ValueError(
                "No personas configured in review personas config. "
                "Run 'sdlc-tools init' or update config/review_personas.yaml.",
            )

        if any(name.lower() == "all" for name in requested):
            return sorted(str(k) for k in personas)

        resolved = list(requested)
        if not resolved:
            primary = str(config.get("primary_persona", "")).strip()
            if not primary:
                raise ValueError(
                    "No persona specified and no primary_persona configured. "
                    "Set primary_persona in config/review_personas.yaml.",
                )
            resolved = [primary]

        missing = [name for name in resolved if name not in personas]
        if missing:
            supported = ", ".join(sorted(str(k) for k in personas))
            raise ValueError(
                f"Unknown persona(s): {', '.join(missing)}. Supported: {supported}",
            )
        return _unique(resolved)

    def load_persona_instructions(self, persona_names: list[str]) -> list[str]:
        """Load instruction text for resolved personas."""
        if not persona_names:
            return []

        config = self._load_persona_config(required=True)
        personas = config.get("personas", {})
        if not isinstance(personas, dict):
            raise ValueError("Invalid review persona config format.")

        instructions: list[str] = []
        for name in persona_names:
            raw_path = str(personas.get(name, "")).strip()
            if not raw_path:
                raise ValueError(f"Persona '{name}' is missing an instruction path.")

            path = Path(raw_path)
            if not path.is_absolute():
                path = Path.cwd() / path
            if not path.is_file():
                raise ValueError(
                    f"Instruction file for persona '{name}' not found: {path}",
                )
            text = path.read_text(encoding="utf-8").strip()
            if not text:
                raise ValueError(f"Instruction file for persona '{name}' is empty: {path}")
            instructions.append(f"[{name}]\n{text}")

        return instructions

    def build_prompt(
        self,
        *,
        mode: str,
        diff: str,
        signals: list[str],
        files_changed: list[str],
        persona_names: list[str] | None = None,
    ) -> str:
        """Build the final prompt from instruction files + analyzer signals + raw diff."""
        base_instruction = self.load_base_instruction(mode).strip()
        sections: list[str] = [base_instruction]

        if mode == "review":
            personas = persona_names or []
            persona_parts = self.load_persona_instructions(personas)
            if persona_parts:
                sections.append("Persona Instructions\n" + "\n\n".join(persona_parts))

        signal_lines = "\n".join(f"- {item}" for item in signals) if signals else "- none"
        file_lines = (
            "\n".join(f"- {path}" for path in files_changed) if files_changed else "- none"
        )
        sections.append("Risk Signals\n" + signal_lines)
        sections.append("Files Changed\n" + file_lines)
        # Keep git diff unchanged and append verbatim.
        sections.append("Git Diff\n" + diff)

        return "\n\n".join(sections)

    def _load_persona_config(self, *, required: bool) -> dict:
        path = self.review_personas_file
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.is_file():
            if required:
                raise ValueError(
                    f"Review personas config file not found: {path}. "
                    "Run 'sdlc-tools init' to scaffold defaults.",
                )
            return {}
        try:
            with open(path, encoding="utf-8") as fh:
                raw = yaml.safe_load(fh)
        except (OSError, yaml.YAMLError) as exc:
            raise ValueError(f"Failed to parse review personas config: {exc}") from exc

        if not isinstance(raw, dict):
            raise ValueError("Review personas config must be a YAML mapping.")
        return raw


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
