"""Tests for the configuration module."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from sdlc_tools.config import SdlcConfig, load_config


class TestSdlcConfigDefaults:
    """Verify default values."""

    def test_defaults(self) -> None:
        cfg = SdlcConfig()
        assert cfg.base_branch == "develop"
        assert cfg.release_prefix == "releases"
        assert cfg.max_diff_length == 20_000
        assert cfg.dry_run is False
        assert cfg.verbose is False
        assert "senior software architect" in cfg.prompt_template.lower()

    def test_custom_prompt_file(self, tmp_path: Path) -> None:
        prompt_file = tmp_path / "my_prompt.txt"
        prompt_file.write_text("Custom prompt: analyse this diff\n", encoding="utf-8")
        cfg = SdlcConfig(prompt_file=str(prompt_file))
        assert cfg.prompt_template == "Custom prompt: analyse this diff\n"

    def test_missing_prompt_file_falls_back_to_default(self) -> None:
        cfg = SdlcConfig(prompt_file="/nonexistent/prompt.txt")
        assert "senior software architect" in cfg.prompt_template.lower()


class TestLoadConfig:
    """Test layered config loading."""

    def test_yaml_file(self, tmp_path: Path) -> None:
        yml = tmp_path / ".sdlc.yml"
        yml.write_text(
            textwrap.dedent("""\
                sdlc:
                  base_branch: releases/2026.3
                  max_diff_length: 5000
            """),
            encoding="utf-8",
        )
        cfg = load_config(config_path=yml)
        assert cfg.base_branch == "releases/2026.3"
        assert cfg.max_diff_length == 5000

    def test_env_overrides_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        yml = tmp_path / ".sdlc.yml"
        yml.write_text("sdlc:\n  base_branch: from-yaml\n", encoding="utf-8")
        monkeypatch.setenv("BASE_BRANCH", "from-env")

        cfg = load_config(config_path=yml)
        assert cfg.base_branch == "from-env"

    def test_cli_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BASE_BRANCH", "from-env")
        cfg = load_config(cli_overrides={"base_branch": "from-cli"})
        assert cfg.base_branch == "from-cli"

    def test_missing_yaml_file(self) -> None:
        cfg = load_config(config_path=Path("/nonexistent/.sdlc.yml"))
        assert cfg.base_branch == "develop"  # fallback to default

    def test_dry_run_coercion(self) -> None:
        cfg = load_config(cli_overrides={"dry_run": "true"})
        assert cfg.dry_run is True

        cfg2 = load_config(cli_overrides={"dry_run": "false"})
        assert cfg2.dry_run is False

    def test_none_cli_values_ignored(self) -> None:
        cfg = load_config(cli_overrides={"base_branch": None, "dry_run": None})
        assert cfg.base_branch == "develop"

    def test_user_global_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """User global config (~/.sdlc/config.yml) merges before project yaml."""
        user_dir = tmp_path / ".sdlc"
        user_dir.mkdir()
        user_cfg = user_dir / "config.yml"
        user_cfg.write_text("sdlc:\n  base_branch: from-user-global\n", encoding="utf-8")

        monkeypatch.setattr("sdlc_tools.config._USER_CONFIG_PATH", user_cfg)

        cfg = load_config(config_path=Path("/nonexistent/.sdlc.yml"))
        assert cfg.base_branch == "from-user-global"

    def test_project_yaml_overrides_user_global(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Project .sdlc.yml takes precedence over user global."""
        user_dir = tmp_path / ".sdlc"
        user_dir.mkdir()
        user_cfg = user_dir / "config.yml"
        user_cfg.write_text("sdlc:\n  base_branch: from-user-global\n", encoding="utf-8")
        monkeypatch.setattr("sdlc_tools.config._USER_CONFIG_PATH", user_cfg)

        project_yml = tmp_path / ".sdlc.yml"
        project_yml.write_text("sdlc:\n  base_branch: from-project\n", encoding="utf-8")

        cfg = load_config(config_path=project_yml)
        assert cfg.base_branch == "from-project"

    def test_prompt_file_via_user_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """prompt_file in user global config is resolved into prompt_template."""
        prompt = tmp_path / "custom.txt"
        prompt.write_text("My custom prompt\n", encoding="utf-8")

        user_dir = tmp_path / ".sdlc"
        user_dir.mkdir()
        user_cfg = user_dir / "config.yml"
        user_cfg.write_text(
            f"sdlc:\n  prompt_file: {prompt}\n", encoding="utf-8",
        )
        monkeypatch.setattr("sdlc_tools.config._USER_CONFIG_PATH", user_cfg)

        cfg = load_config(config_path=Path("/nonexistent/.sdlc.yml"))
        assert cfg.prompt_template == "My custom prompt\n"
