"""Tests for the ``sdlc-tools init`` command."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from sdlc_tools.cli import main


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
            assert Path(".github/workflows/ai-report.yml").is_file()
            assert Path(".github/workflows/release-tag.yml").is_file()
            assert "Created 10 file(s)" in result.output

    def test_skips_existing_sdlc_yml(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path(".sdlc.yml").write_text("existing", encoding="utf-8")
            result = runner.invoke(main, ["init"])
            assert result.exit_code == 0
            assert "skip  .sdlc.yml" in result.output
            assert Path(".sdlc.yml").read_text(encoding="utf-8") == "existing"
            assert "Created 9 file(s)" in result.output

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
            assert "Created 9 file(s)" in result.output

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
            assert not Path(".github").exists()
            assert "Created 8 file(s)" in result.output

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
