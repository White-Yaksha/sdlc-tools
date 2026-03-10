"""Tests for the ``sdlc-tools init`` command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from sdlc_tools.cli import (
    _prompt_optional_bundle_selection,
    _prompt_optional_mode_with_arrows,
    main,
)


class TestInit:
    """Verify init scaffolds .sdlc.yml + workflow files."""

    def test_creates_all_files(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, ["init"])
            assert result.exit_code == 0
            assert Path(".sdlc.yml").is_file()
            sdlc_yml = Path(".sdlc.yml").read_text(encoding="utf-8")
            assert "release_tag_name" in sdlc_yml
            assert "github_event_name" in sdlc_yml
            assert "github_event_path" in sdlc_yml
            assert Path("config/risk_rules.yaml").is_file()
            assert Path("config/review_personas.yaml").is_file()
            assert Path("instructions/report/report_base.md").is_file()
            assert Path("instructions/review/review_base.md").is_file()
            assert Path("instructions/review/personas/security.md").is_file()
            assert Path("instructions/review/personas/performance.md").is_file()
            assert Path("instructions/review/personas/architecture.md").is_file()
            assert Path("event.json").is_file()
            assert Path(".github/workflows/ai-report.yml").is_file()
            assert Path(".github/workflows/release-tag.yml").is_file()
            assert "Created 11 file(s)" in result.output

    def test_skips_existing_sdlc_yml(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path(".sdlc.yml").write_text("existing", encoding="utf-8")
            result = runner.invoke(main, ["init"])
            assert result.exit_code == 0
            assert "skip  .sdlc.yml" in result.output
            assert Path(".sdlc.yml").read_text(encoding="utf-8") == "existing"
            assert "Created 10 file(s)" in result.output

    def test_skips_existing_workflows(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            wf_dir = Path(".github/workflows")
            wf_dir.mkdir(parents=True)
            (wf_dir / "ai-report.yml").write_text("existing", encoding="utf-8")
            result = runner.invoke(main, ["init"])
            assert result.exit_code == 0
            assert "skip  .github/workflows/ai-report.yml" in result.output
            assert (wf_dir / "ai-report.yml").read_text(encoding="utf-8") == "existing"
            assert (wf_dir / "release-tag.yml").is_file()
            assert "Created 10 file(s)" in result.output

    def test_all_exist_nothing_created(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path(".sdlc.yml").write_text("x", encoding="utf-8")
            wf_dir = Path(".github/workflows")
            wf_dir.mkdir(parents=True)
            (wf_dir / "ai-report.yml").write_text("x", encoding="utf-8")
            (wf_dir / "release-tag.yml").write_text("x", encoding="utf-8")
            Path("config").mkdir(parents=True, exist_ok=True)
            Path("config/risk_rules.yaml").write_text("x", encoding="utf-8")
            Path("config/review_personas.yaml").write_text("x", encoding="utf-8")
            Path("instructions/report").mkdir(parents=True, exist_ok=True)
            Path("instructions/review/personas").mkdir(parents=True, exist_ok=True)
            Path("instructions/report/report_base.md").write_text("x", encoding="utf-8")
            Path("instructions/review/review_base.md").write_text("x", encoding="utf-8")
            Path("instructions/review/personas/security.md").write_text("x", encoding="utf-8")
            Path("instructions/review/personas/performance.md").write_text("x", encoding="utf-8")
            Path("instructions/review/personas/architecture.md").write_text("x", encoding="utf-8")
            Path("event.json").write_text("x", encoding="utf-8")
            result = runner.invoke(main, ["init"])
            assert result.exit_code == 0
            assert "Nothing to create" in result.output

    def test_skip_workflows_flag(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, ["init", "--skip-workflows"])
            assert result.exit_code == 0
            assert Path(".sdlc.yml").is_file()
            assert Path("config/risk_rules.yaml").is_file()
            assert Path("config/review_personas.yaml").is_file()
            assert Path("instructions/report/report_base.md").is_file()
            assert Path("instructions/review/review_base.md").is_file()
            assert Path("event.json").is_file()
            assert not Path(".github").exists()
            assert "Created 9 file(s)" in result.output

    def test_populates_repository_from_env(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                main,
                ["init", "--skip-workflows"],
                env={"GITHUB_REPOSITORY": "rez-one/wtg-events-api-intg"},
            )
            assert result.exit_code == 0
            sdlc_yml = Path(".sdlc.yml").read_text(encoding="utf-8")
            assert "github_repository: rez-one/wtg-events-api-intg" in sdlc_yml

    def test_select_none_creates_only_mandatory_files(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, ["init", "--optional", "select-none"])
            assert result.exit_code == 0
            assert Path(".sdlc.yml").is_file()
            assert Path("instructions/report/report_base.md").is_file()
            assert Path("instructions/review/review_base.md").is_file()
            assert not Path("config/risk_rules.yaml").exists()
            assert not Path("config/review_personas.yaml").exists()
            assert not Path("instructions/review/personas/security.md").exists()
            assert not Path(".github/workflows/ai-report.yml").exists()
            assert not Path("event.json").exists()
            assert "Created 3 file(s)" in result.output

    def test_select_review_personas_creates_persona_bundle(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, ["init", "--optional", "review-personas"])
            assert result.exit_code == 0
            assert Path(".sdlc.yml").is_file()
            assert Path("instructions/report/report_base.md").is_file()
            assert Path("instructions/review/review_base.md").is_file()
            assert Path("config/review_personas.yaml").is_file()
            assert Path("instructions/review/personas/security.md").is_file()
            assert Path("instructions/review/personas/performance.md").is_file()
            assert Path("instructions/review/personas/architecture.md").is_file()
            assert not Path("config/risk_rules.yaml").exists()
            assert not Path(".github/workflows/ai-report.yml").exists()
            assert not Path("event.json").exists()
            assert "Created 7 file(s)" in result.output

    def test_select_local_tag_event_json_creates_event_file(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, ["init", "--optional", "local-tag-event-json"])
            assert result.exit_code == 0
            assert Path("event.json").is_file()
            assert "Created 4 file(s)" in result.output

    def test_select_workflow_with_skip_workflows_excludes_workflow(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                main,
                ["init", "--optional", "ai-report-workflow", "--skip-workflows"],
            )
            assert result.exit_code == 0
            assert not Path(".github/workflows/ai-report.yml").exists()
            assert (
                "[INFO] --skip-workflows is set; workflow bundles were excluded."
                in result.output
            )
            assert "Created 3 file(s)" in result.output

    def test_select_all_creates_all_optional_files(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, ["init", "--optional", "select-all"])
            assert result.exit_code == 0
            assert Path("config/risk_rules.yaml").is_file()
            assert Path("config/review_personas.yaml").is_file()
            assert Path(".github/workflows/ai-report.yml").is_file()
            assert Path(".github/workflows/release-tag.yml").is_file()
            assert Path("event.json").is_file()
            assert "Created 11 file(s)" in result.output

    def test_workflow_content_valid_yaml(self, tmp_path: Path) -> None:
        import yaml

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(main, ["init"])
            for name in ("ai-report.yml", "release-tag.yml"):
                path = Path(".github/workflows") / name
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                assert "name" in data
                assert True in data  # YAML parses `on:` as boolean True
                assert "jobs" in data


class TestInitInteractiveSelection:
    """Verify interactive init selector behavior."""

    def test_mode_selector_renders_highlighted_list(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        keys = iter(["\r"])
        with patch("sdlc_tools.cli._supports_ansi_redraw", return_value=False):
            mode = _prompt_optional_mode_with_arrows(key_reader=lambda: next(keys))
        assert mode == "select-all"
        output = capsys.readouterr().out
        assert "> Select all optional bundles" in output
        assert "Select none (mandatory files only)" in output
        assert "Custom per-bundle selection (y/N prompts)" in output

    def test_mode_selector_down_then_enter_selects_none(self) -> None:
        keys = iter(["\x1b[B", "\r"])
        mode = _prompt_optional_mode_with_arrows(key_reader=lambda: next(keys))
        assert mode == "select-none"

    def test_mode_selector_windows_arrows_selects_custom(self) -> None:
        keys = iter(["\xe0", "P", "\xe0", "P", "\r"])
        mode = _prompt_optional_mode_with_arrows(key_reader=lambda: next(keys))
        assert mode == "custom"

    def test_mode_selector_windows_combined_arrow_code_selects_none(self) -> None:
        keys = iter(["\xe0P", "\r"])
        mode = _prompt_optional_mode_with_arrows(key_reader=lambda: next(keys))
        assert mode == "select-none"

    def test_prompt_optional_bundle_selection_custom_yn(self) -> None:
        with (
            patch("sdlc_tools.cli._prompt_optional_mode_with_arrows", return_value="custom"),
            patch(
                "sdlc_tools.cli.click.confirm",
                side_effect=[True, False, True, False, True],
            ),
        ):
            selected = _prompt_optional_bundle_selection()
        assert selected == [
            "risk-rules",
            "ai-report-workflow",
            "local-tag-event-json",
        ]
