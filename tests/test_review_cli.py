"""Tests for review CLI command options."""

from __future__ import annotations

from click.testing import CliRunner

from sdlc_tools.cli import main


class _DummyClient:
    def __init__(self, token: str = "", *, dry_run: bool = False) -> None:
        self.token = token
        self.dry_run = dry_run


class _DummyGenerator:
    called_personas: list[str] | None = None
    called_branch: str | None = None

    def __init__(self, client: _DummyClient, config: object) -> None:
        self.client = client
        self.config = config

    def review(
        self,
        *,
        personas: list[str] | None = None,
        branch: str | None = None,
    ) -> None:
        _DummyGenerator.called_personas = personas or []
        _DummyGenerator.called_branch = branch


class TestReviewCli:
    def test_persona_options_forwarded(self, monkeypatch) -> None:
        _DummyGenerator.called_personas = None
        _DummyGenerator.called_branch = None
        monkeypatch.setattr("sdlc_tools.client.GitHubClient", _DummyClient)
        monkeypatch.setattr("sdlc_tools.report.ReportGenerator", _DummyGenerator)

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["review", "--persona", "security", "--persona", "performance"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert _DummyGenerator.called_personas == ["security", "performance"]

    def test_no_persona_forwards_empty_list(self, monkeypatch) -> None:
        _DummyGenerator.called_personas = None
        _DummyGenerator.called_branch = None
        monkeypatch.setattr("sdlc_tools.client.GitHubClient", _DummyClient)
        monkeypatch.setattr("sdlc_tools.report.ReportGenerator", _DummyGenerator)

        runner = CliRunner()
        result = runner.invoke(main, ["review"], catch_exceptions=False)
        assert result.exit_code == 0
        assert _DummyGenerator.called_personas == []

    def test_branch_option_forwarded(self, monkeypatch) -> None:
        _DummyGenerator.called_branch = None
        monkeypatch.setattr("sdlc_tools.client.GitHubClient", _DummyClient)
        monkeypatch.setattr("sdlc_tools.report.ReportGenerator", _DummyGenerator)

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["review", "--branch", "feature/xyz"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert _DummyGenerator.called_branch == "feature/xyz"

    def test_no_branch_forwards_none(self, monkeypatch) -> None:
        _DummyGenerator.called_branch = None
        monkeypatch.setattr("sdlc_tools.client.GitHubClient", _DummyClient)
        monkeypatch.setattr("sdlc_tools.report.ReportGenerator", _DummyGenerator)

        runner = CliRunner()
        result = runner.invoke(main, ["review"], catch_exceptions=False)
        assert result.exit_code == 0
        assert _DummyGenerator.called_branch is None

    def test_push_option_removed(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["review", "--push"])
        assert result.exit_code != 0
        assert "No such option" in result.output or "no such option" in result.output

    def test_force_push_option_removed(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["review", "--force-push"])
        assert result.exit_code != 0
        assert "No such option" in result.output or "no such option" in result.output
