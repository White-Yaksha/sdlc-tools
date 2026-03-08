"""Tests for the setup command and token validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import responses
import yaml
from click.testing import CliRunner

from sdlc_tools.cli import main
from sdlc_tools.client import GitHubClient


class TestValidateToken:
    """Tests for GitHubClient.validate_token."""

    @responses.activate
    def test_valid_token(self) -> None:
        responses.add(
            responses.GET,
            "https://api.github.com/user",
            json={"login": "testuser", "name": "Test User"},
            headers={"X-OAuth-Scopes": "repo, workflow"},
            status=200,
        )
        result = GitHubClient.validate_token("ghp_valid")
        assert result["login"] == "testuser"
        assert result["name"] == "Test User"
        assert "repo" in result["scopes"]

    @responses.activate
    def test_invalid_token_401(self) -> None:
        responses.add(
            responses.GET,
            "https://api.github.com/user",
            json={"message": "Bad credentials"},
            status=401,
        )
        with pytest.raises(ValueError, match="Invalid GitHub token"):
            GitHubClient.validate_token("ghp_bad")

    @responses.activate
    def test_forbidden_token_403(self) -> None:
        responses.add(
            responses.GET,
            "https://api.github.com/user",
            json={"message": "Forbidden"},
            status=403,
        )
        with pytest.raises(ValueError, match="lacks required permissions"):
            GitHubClient.validate_token("ghp_noperm")


class TestSetupCommand:
    """Tests for sdlc-tools setup CLI command."""

    @responses.activate
    def test_setup_with_token_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        user_dir = tmp_path / ".sdlc"
        monkeypatch.setattr("sdlc_tools.config._USER_CONFIG_DIR", user_dir)
        monkeypatch.setattr("sdlc_tools.config._USER_CONFIG_PATH", user_dir / "config.yml")

        responses.add(
            responses.GET,
            "https://api.github.com/user",
            json={"login": "myuser", "name": "My User"},
            headers={"X-OAuth-Scopes": "repo"},
            status=200,
        )

        runner = CliRunner()
        result = runner.invoke(main, ["setup", "--token", "ghp_test123"])
        assert result.exit_code == 0
        assert "Authenticated as myuser" in result.output

        cfg_file = user_dir / "config.yml"
        assert cfg_file.is_file()
        data = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
        assert data["sdlc"]["github_token"] == "ghp_test123"

    @responses.activate
    def test_setup_with_prompt_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        user_dir = tmp_path / ".sdlc"
        monkeypatch.setattr("sdlc_tools.config._USER_CONFIG_DIR", user_dir)
        monkeypatch.setattr("sdlc_tools.config._USER_CONFIG_PATH", user_dir / "config.yml")

        prompt = tmp_path / "my_prompt.txt"
        prompt.write_text("Custom prompt\n", encoding="utf-8")

        responses.add(
            responses.GET,
            "https://api.github.com/user",
            json={"login": "dev", "name": ""},
            headers={"X-OAuth-Scopes": ""},
            status=200,
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["setup", "--token", "ghp_abc", "--prompt-file", str(prompt)],
        )
        assert result.exit_code == 0

        data = yaml.safe_load((user_dir / "config.yml").read_text(encoding="utf-8"))
        assert data["sdlc"]["prompt_file"] == str(prompt)

    @responses.activate
    def test_setup_invalid_token(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        user_dir = tmp_path / ".sdlc"
        monkeypatch.setattr("sdlc_tools.config._USER_CONFIG_DIR", user_dir)
        monkeypatch.setattr("sdlc_tools.config._USER_CONFIG_PATH", user_dir / "config.yml")

        responses.add(
            responses.GET,
            "https://api.github.com/user",
            json={"message": "Bad credentials"},
            status=401,
        )

        runner = CliRunner()
        result = runner.invoke(main, ["setup", "--token", "ghp_bad"])
        assert result.exit_code == 1
        assert "Invalid GitHub token" in result.output

    @responses.activate
    def test_setup_merges_existing_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Setup should merge into existing config, not overwrite it."""
        user_dir = tmp_path / ".sdlc"
        user_dir.mkdir()
        cfg_file = user_dir / "config.yml"
        cfg_file.write_text(
            "sdlc:\n  base_branch: main\n", encoding="utf-8",
        )
        monkeypatch.setattr("sdlc_tools.config._USER_CONFIG_DIR", user_dir)
        monkeypatch.setattr("sdlc_tools.config._USER_CONFIG_PATH", cfg_file)

        responses.add(
            responses.GET,
            "https://api.github.com/user",
            json={"login": "dev", "name": ""},
            headers={"X-OAuth-Scopes": ""},
            status=200,
        )

        runner = CliRunner()
        result = runner.invoke(main, ["setup", "--token", "ghp_new"])
        assert result.exit_code == 0

        data = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
        assert data["sdlc"]["github_token"] == "ghp_new"
        assert data["sdlc"]["base_branch"] == "main"

    @responses.activate
    def test_setup_fresh_writes_full_template(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """First-time setup should write a fully-commented config template."""
        user_dir = tmp_path / ".sdlc"
        monkeypatch.setattr("sdlc_tools.config._USER_CONFIG_DIR", user_dir)
        monkeypatch.setattr("sdlc_tools.config._USER_CONFIG_PATH", user_dir / "config.yml")

        responses.add(
            responses.GET,
            "https://api.github.com/user",
            json={"login": "dev", "name": ""},
            headers={"X-OAuth-Scopes": "repo"},
            status=200,
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["setup", "--token", "ghp_fresh", "--provider", "gemini"],
        )
        assert result.exit_code == 0

        content = (user_dir / "config.yml").read_text(encoding="utf-8")
        # Active values should be uncommented.
        assert "  github_token: ghp_fresh" in content
        assert "  ai_provider: gemini" in content
        # Unused values should remain commented.
        assert "  # ai_model:" in content
        assert "  # dry_run:" in content
        assert "  # base_branch:" in content
        # Should still parse as valid YAML.
        data = yaml.safe_load(content)
        assert data["sdlc"]["github_token"] == "ghp_fresh"
        assert data["sdlc"]["ai_provider"] == "gemini"
