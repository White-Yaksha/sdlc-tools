"""Layered configuration: user global → .sdlc.yml → environment variables → CLI arguments."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from sdlc_tools.prompts import load_prompt

_DEFAULT_CONFIG_FILENAME = ".sdlc.yml"
_USER_CONFIG_DIR = Path.home() / ".sdlc"
_USER_CONFIG_PATH = _USER_CONFIG_DIR / "config.yml"
_COMMENT_MARKER = "<!-- AI-SDLC-REPORT -->"


@dataclass
class SdlcConfig:
    """Resolved SDLC configuration with layered precedence."""

    base_branch: str = "develop"
    release_prefix: str = "releases"
    release_tag_name: str = ""
    max_diff_length: int = 20_000
    comment_marker: str = _COMMENT_MARKER
    dry_run: bool = False
    verbose: bool = False
    log_file: str = ""
    github_token: str = ""
    github_repository: str = ""
    github_event_name: str = ""
    github_event_path: str = ""
    # Path to a custom prompt file (empty → use bundled default).
    prompt_file: str = ""
    # AI provider settings.
    ai_provider: str = "copilot"
    ai_model: str = ""
    ai_api_key: str = ""
    ai_base_url: str = ""
    ai_timeout: int = 120
    # Resolved prompt template (populated in __post_init__).
    prompt_template: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if not self.prompt_template:
            self.prompt_template = load_prompt(self.prompt_file)


def _load_user_global_config() -> dict:
    """Load user-global config from ``~/.sdlc/config.yml``."""
    return _load_yaml_file(_USER_CONFIG_PATH)


def _load_yaml_file(path: Path) -> dict:
    """Load a YAML file and return its ``sdlc:`` section (or empty dict)."""
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
            sdlc = data.get("sdlc", {}) if isinstance(data, dict) else {}
            return sdlc if isinstance(sdlc, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}


def _load_yaml_config(config_path: Path | None = None) -> dict:
    """Load project configuration from a YAML file."""
    if config_path is None:
        config_path = Path.cwd() / _DEFAULT_CONFIG_FILENAME
    return _load_yaml_file(config_path)


def _load_env_overrides() -> dict:
    """Read configuration overrides from environment variables."""
    mapping = {
        "BASE_BRANCH": "base_branch",
        "RELEASE_PREFIX": "release_prefix",
        "RELEASE_TAG_NAME": "release_tag_name",
        "MAX_DIFF_LENGTH": "max_diff_length",
        "COMMENT_MARKER": "comment_marker",
        "GITHUB_TOKEN": "github_token",
        "GITHUB_REPOSITORY": "github_repository",
        "GITHUB_EVENT_NAME": "github_event_name",
        "GITHUB_EVENT_PATH": "github_event_path",
        "AI_PROVIDER": "ai_provider",
        "AI_MODEL": "ai_model",
        "AI_API_KEY": "ai_api_key",
        "AI_BASE_URL": "ai_base_url",
        "AI_TIMEOUT": "ai_timeout",
    }
    overrides: dict = {}
    for env_key, config_key in mapping.items():
        value = os.environ.get(env_key)
        if value is not None:
            overrides[config_key] = value
    return overrides


def load_config(
    config_path: Path | None = None,
    cli_overrides: dict | None = None,
) -> SdlcConfig:
    """Build an SdlcConfig by merging five configuration layers.

    Precedence (lowest → highest):
      code defaults → user global (~/.sdlc/config.yml) → project .sdlc.yml → env → CLI.
    """
    merged: dict = {}

    # Layer 1: code defaults are handled by the SdlcConfig dataclass.

    # Layer 2: User global config (~/.sdlc/config.yml).
    merged.update(_load_user_global_config())

    # Layer 3: Project YAML file (.sdlc.yml).
    merged.update(_load_yaml_config(config_path))

    # Layer 4: Environment variable overrides.
    merged.update(_load_env_overrides())

    # Layer 5: CLI argument overrides.
    if cli_overrides:
        merged.update({k: v for k, v in cli_overrides.items() if v is not None})

    # Coerce types.
    if "max_diff_length" in merged:
        merged["max_diff_length"] = int(merged["max_diff_length"])
    if "ai_timeout" in merged:
        merged["ai_timeout"] = int(merged["ai_timeout"])
    if "dry_run" in merged:
        merged["dry_run"] = str(merged["dry_run"]).lower() in ("true", "1", "yes")
    if "verbose" in merged:
        merged["verbose"] = str(merged["verbose"]).lower() in ("true", "1", "yes")

    # Filter to only valid SdlcConfig fields.
    valid_fields = {f.name for f in SdlcConfig.__dataclass_fields__.values()}
    filtered = {k: v for k, v in merged.items() if k in valid_fields}

    return SdlcConfig(**filtered)
