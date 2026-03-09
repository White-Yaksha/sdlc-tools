"""CLI entry point — ``sdlc-tools`` command with subcommands."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click

from sdlc_tools import __version__
from sdlc_tools.config import SdlcConfig, load_config
from sdlc_tools.log import setup_logging


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--dry-run", is_flag=True, default=False, help="Preview without side effects.")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enable debug logging.")
@click.option("--config", "config_path", type=click.Path(exists=False), default=None,
              help="Path to .sdlc.yml config file.")
@click.option("--log-file", default="", help="Write logs to a file.")
@click.version_option(version=__version__, prog_name="sdlc-tools")
@click.pass_context
def main(
    ctx: click.Context,
    dry_run: bool,
    verbose: bool,
    config_path: str | None,
    log_file: str,
) -> None:
    """SDLC Tools — A developer CLI for SDLC automation."""
    setup_logging(verbose=verbose, log_file=log_file)

    cfg_path = Path(config_path) if config_path else None
    ctx.ensure_object(dict)
    ctx.obj["cli_overrides"] = {
        "dry_run": dry_run or None,
        "verbose": verbose or None,
        "log_file": log_file or None,
    }
    ctx.obj["config_path"] = cfg_path


def _build_config(ctx: click.Context, extra: dict | None = None) -> SdlcConfig:
    """Resolve config from context + any command-specific overrides."""
    overrides = {**ctx.obj["cli_overrides"]}
    if extra:
        overrides.update(extra)
    return load_config(config_path=ctx.obj["config_path"], cli_overrides=overrides)


def _log_config(config: SdlcConfig, command: str) -> None:
    """Log key resolved config values for debugging."""
    click.echo(f"[CONFIG] command={command}")
    click.echo(f"[CONFIG] base_branch={config.base_branch}")
    click.echo(f"[CONFIG] ai_provider={config.ai_provider}")
    if config.ai_model:
        click.echo(f"[CONFIG] ai_model={config.ai_model}")
    click.echo(f"[CONFIG] release_prefix={config.release_prefix}")
    if config.release_tag_name:
        click.echo(f"[CONFIG] release_tag_name={config.release_tag_name}")
    click.echo(f"[CONFIG] max_diff_length={config.max_diff_length}")
    click.echo(f"[CONFIG] dry_run={config.dry_run}")
    if config.github_repository:
        click.echo(f"[CONFIG] repository={config.github_repository}")


# -----------------------------------------------------------------------
# report
# -----------------------------------------------------------------------


@main.command()
@click.option("--base-branch", default=None, help="Base branch for diff (overrides config).")
@click.option("--provider", "ai_provider", default=None,
              help="AI provider: copilot, openai, anthropic, gemini, ollama.")
@click.option("--model", "ai_model", default=None, help="AI model name (overrides config).")
@click.option("--push", "push_first", is_flag=True, default=False,
              help="Push the current branch to origin before generating the report.")
@click.option("--force-push", "force_push", is_flag=True, default=False,
              help="Force-push the current branch (implies --push).")
@click.option("--last-commit", "last_commit", is_flag=True, default=False,
              help="Analyze only the latest commit instead of the full branch diff.")
@click.option("--commit", "commit_sha", default=None,
              help="Analyze a specific commit by SHA.")
@click.option("--commit-wise", "commit_wise", is_flag=True, default=False,
              help="Analyze each commit individually and post a consolidated full report.")
@click.pass_context
def report(
    ctx: click.Context,
    base_branch: str | None,
    ai_provider: str | None,
    ai_model: str | None,
    push_first: bool,
    force_push: bool,
    last_commit: bool,
    commit_sha: str | None,
    commit_wise: bool,
) -> None:
    """Generate an AI code impact report and post it to the PR."""
    from sdlc_tools.client import GitHubClient
    from sdlc_tools.report import ReportGenerator

    exclusive_count = sum([last_commit, bool(commit_sha), commit_wise])
    if exclusive_count > 1:
        click.echo(
            "[ERROR] --last-commit, --commit, and --commit-wise are mutually exclusive.",
            err=True,
        )
        sys.exit(1)

    if push_first or force_push:
        from sdlc_tools.git import push_current_branch

        if not push_current_branch(force=force_push):
            click.echo("[ERROR] Git push failed. Aborting report.", err=True)
            sys.exit(1)

    # Resolve commit SHA for commit-level reports.
    resolved_sha: str | None = commit_sha
    if last_commit:
        from sdlc_tools.git import get_last_commit_sha

        resolved_sha = get_last_commit_sha()

    config = _build_config(ctx, {
        "base_branch": base_branch,
        "ai_provider": ai_provider,
        "ai_model": ai_model,
    })
    _log_config(config, "report")

    try:
        client = GitHubClient(token=config.github_token, dry_run=config.dry_run)
    except ValueError as exc:
        click.echo(f"[ERROR] {exc}", err=True)
        sys.exit(1)

    generator = ReportGenerator(client, config)
    if commit_wise:
        generator.run_commit_wise()
    else:
        generator.run(commit_sha=resolved_sha)


# -----------------------------------------------------------------------
# tag
# -----------------------------------------------------------------------


@main.command()
@click.option("--tag-name", default=None, help="Tag name to create (overrides config).")
@click.option("--event-path", default=None, help="Path to GitHub event JSON (CI only).")
@click.pass_context
def tag(ctx: click.Context, tag_name: str | None, event_path: str | None) -> None:
    """Create or update a release tag (CI workflow command)."""
    from sdlc_tools.client import GitHubClient
    from sdlc_tools.tagger import TagManager

    config = _build_config(ctx, {
        "release_tag_name": tag_name,
        "github_event_path": event_path,
    })
    _log_config(config, "tag")

    try:
        client = GitHubClient(token=config.github_token, dry_run=config.dry_run)
    except ValueError as exc:
        click.echo(f"[ERROR] {exc}", err=True)
        sys.exit(1)

    owner, repo = "", ""
    if config.github_repository and "/" in config.github_repository:
        owner, repo = config.github_repository.split("/", 1)
    else:
        click.echo("[ERROR] GITHUB_REPOSITORY is not set or invalid.", err=True)
        sys.exit(1)

    manager = TagManager(client, config)

    if config.github_event_name == "pull_request":
        manager.handle_event(owner, repo)
    else:
        click.echo(
            f"[INFO] Event '{config.github_event_name}' is not handled. No action taken.",
        )


# -----------------------------------------------------------------------
# init — templates
# -----------------------------------------------------------------------

_SDLC_YML_TEMPLATE = """\
# SDLC Tools — Project Configuration
# This file contains project-specific settings (committed to git).
# User-level settings (token, AI keys) live in ~/.sdlc/config.yml
# (run: sdlc-tools setup).
#
# Config precedence (lowest → highest):
#   code defaults → ~/.sdlc/config.yml → .sdlc.yml → env vars → CLI args
#
# See: https://github.com/White-Yaksha/sdlc-tools

sdlc:
  # ── Branch & Release ──────────────────────────────────────
  # base_branch: develop              # Branch to diff against
  # release_prefix: releases          # PR branch prefix for auto-tagging

  # ── Report Settings ───────────────────────────────────────
  # max_diff_length: 20000            # Truncate diff beyond this (chars)
  # comment_marker: "<!-- AI-SDLC-REPORT -->"  # HTML marker for idempotent PR comments

  # ── AI Provider ───────────────────────────────────────────
  # ai_provider: copilot              # copilot & ollama: local only; CI: openai|anthropic|gemini
  # ai_model: ""                      # Model name (provider default if empty)
  # ai_api_key: ""                    # API key (prefer env var or ~/.sdlc/config.yml)
  # ai_base_url: ""                   # Custom endpoint / proxy URL
  # ai_timeout: 120                   # Request timeout in seconds

  # ── Prompt ────────────────────────────────────────────────
  # prompt_file: ""                   # Path to custom prompt (empty → bundled default)

  # ── Behaviour ─────────────────────────────────────────────
  # dry_run: false                    # Preview without side effects
  # verbose: false                    # Enable debug logging
  # log_file: ""                      # Write logs to file
"""

_WORKFLOW_TEMPLATES: dict[str, str] = {
    "ai-report.yml": """\
# Generated by sdlc-tools init
# AI Code Impact Report — posts an AI-generated diff analysis on every PR.
name: AI Code Impact Report

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  report:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - run: pip install git+https://github.com/White-Yaksha/sdlc-tools.git

      - run: sdlc-tools report --base-branch ${{ github.base_ref }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

          # ── AI Provider (uncomment one provider block) ─────────
          AI_PROVIDER: gemini
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          # AI_PROVIDER: openai
          # OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          # AI_PROVIDER: anthropic
          # ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          # AI_PROVIDER: copilot       # ⚠ LOCAL ONLY — not supported in CI
          # AI_PROVIDER: ollama        # ⚠ LOCAL ONLY — needs self-hosted runner with Ollama

          # ── AI Model (optional, uses provider default if empty)
          # AI_MODEL: ""

          # ── AI Custom Endpoint (optional, for proxies) ─────────
          # AI_BASE_URL: ""
          # AI_TIMEOUT: "120"

          # ── Report Settings ────────────────────────────────────
          # BASE_BRANCH: develop
          # MAX_DIFF_LENGTH: "20000"
          # COMMENT_MARKER: "<!-- AI-SDLC-REPORT -->"

          # ── Behaviour ──────────────────────────────────────────
          # DRY_RUN: "false"
""",
    "release-tag.yml": """\
# Generated by sdlc-tools init
# Release Tag — creates a Git tag when a PR into releases/** is merged.
name: Release Tag

on:
  pull_request:
    types: [closed]
    branches:
      - 'releases/**'

jobs:
  tag:
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - run: pip install git+https://github.com/White-Yaksha/sdlc-tools.git

      - run: sdlc-tools tag
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          RELEASE_TAG_NAME: ${{ vars.RELEASE_TAG_NAME }}

          # ── Release Settings ───────────────────────────────────
          # RELEASE_PREFIX: releases

          # ── Behaviour ──────────────────────────────────────────
          # DRY_RUN: "false"
""",
}

# -----------------------------------------------------------------------
# init
# -----------------------------------------------------------------------


@main.command()
@click.option(
    "--skip-workflows", is_flag=True, default=False,
    help="Skip generating GitHub Actions workflow files.",
)
@click.pass_context
def init(ctx: click.Context, skip_workflows: bool) -> None:
    """Create .sdlc.yml and GitHub Actions workflows in the current directory."""
    created: list[str] = []

    # --- .sdlc.yml ---
    sdlc_yml = Path.cwd() / ".sdlc.yml"
    if sdlc_yml.exists():
        click.echo("  skip  .sdlc.yml (already exists)")
    else:
        sdlc_yml.write_text(_SDLC_YML_TEMPLATE, encoding="utf-8")
        created.append(str(sdlc_yml))
        click.echo(f"  create  {sdlc_yml}")

    # --- GitHub Actions workflows ---
    if not skip_workflows:
        workflows_dir = Path.cwd() / ".github" / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)

        for filename, content in _WORKFLOW_TEMPLATES.items():
            wf = workflows_dir / filename
            if wf.exists():
                click.echo(f"  skip  .github/workflows/{filename} (already exists)")
            else:
                wf.write_text(content, encoding="utf-8")
                created.append(str(wf))
                click.echo(f"  create  .github/workflows/{filename}")

    if created:
        count = len(created)
        click.echo(f"\n✓ Created {count} file(s). Run 'sdlc-tools setup' to configure credentials.")
    else:
        click.echo("\nNothing to create — all files already exist.")


# -----------------------------------------------------------------------
# setup — helpers
# -----------------------------------------------------------------------


def _build_user_config_template(values: dict) -> str:
    """Build a fully-commented ``~/.sdlc/config.yml`` with active values filled in."""
    def _line(key: str, default: str) -> str:
        val = values.get(key)
        if val is not None:
            return f"  {key}: {val}"
        return f"  # {key}: {default}"

    return (
        "# SDLC Tools — User Configuration\n"
        "# Personal settings (NOT committed to git).\n"
        "# Created by: sdlc-tools setup\n"
        "#\n"
        "# Config precedence (lowest → highest):\n"
        "#   code defaults → ~/.sdlc/config.yml → .sdlc.yml → env vars → CLI args\n"
        "#\n"
        "# See: https://github.com/White-Yaksha/sdlc-tools\n"
        "\n"
        "sdlc:\n"
        "  # ── Authentication ────────────────────────────────────\n"
        + _line("github_token", "<your-token>") + "\n"
        "\n"
        "  # ── AI Provider ───────────────────────────────────────\n"
        + _line("ai_provider", "copilot") + "\n"
        + _line("ai_model", '""') + "\n"
        + _line("ai_api_key", '""') + "\n"
        + _line("ai_base_url", '""') + "\n"
        + _line("ai_timeout", "120") + "\n"
        "\n"
        "  # ── Prompt ────────────────────────────────────────────\n"
        + _line("prompt_file", '""') + "\n"
        "\n"
        "  # ── Branch & Release (override project .sdlc.yml) ────\n"
        "  # base_branch: develop\n"
        "  # release_prefix: releases\n"
        "\n"
        "  # ── Report Settings ───────────────────────────────────\n"
        "  # max_diff_length: 20000\n"
        '  # comment_marker: "<!-- AI-SDLC-REPORT -->"\n'
        "\n"
        "  # ── Behaviour ─────────────────────────────────────────\n"
        "  # dry_run: false\n"
        "  # verbose: false\n"
        "  # log_file: \"\"\n"
    )


def _restrict_file_permissions(path: Path) -> None:
    """Set file to owner-only read/write (0o600) on Unix. No-op on Windows."""
    if os.name != "nt":
        path.chmod(0o600)


# -----------------------------------------------------------------------
# setup
# -----------------------------------------------------------------------


@main.command()
@click.option("--token", default=None, help="GitHub personal access token.")
@click.option(
    "--prompt-file", default=None,
    help="Path to a custom Copilot prompt file.",
)
@click.option("--provider", "ai_provider", default=None,
              help="AI provider: copilot, openai, anthropic, gemini, ollama.")
@click.option("--model", "ai_model", default=None, help="Default AI model name.")
@click.option("--ai-key", "ai_api_key", default=None, help="API key for the AI provider.")
def setup(
    token: str | None,
    prompt_file: str | None,
    ai_provider: str | None,
    ai_model: str | None,
    ai_api_key: str | None,
) -> None:
    """Set up user-level config at ~/.sdlc/config.yml (token + prompt + AI)."""
    from sdlc_tools.client import GitHubClient
    from sdlc_tools.config import _USER_CONFIG_DIR, _USER_CONFIG_PATH

    # --- Resolve token ---
    resolved_token = token
    if not resolved_token:
        click.echo("Auto-detecting GitHub token...")
        resolved_token = GitHubClient._resolve_token()

    if not resolved_token:
        resolved_token = click.prompt("Enter your GitHub Personal Access Token", hide_input=True)

    if not resolved_token:
        click.echo("[ERROR] No token provided. Aborting.", err=True)
        sys.exit(1)

    # --- Validate token ---
    try:
        user_info = GitHubClient.validate_token(resolved_token)
    except ValueError as exc:
        click.echo(f"[ERROR] {exc}", err=True)
        sys.exit(1)

    click.echo(f"✓ Authenticated as {user_info['login']}"
               + (f" ({user_info['name']})" if user_info.get("name") else ""))

    if user_info.get("scopes"):
        click.echo(f"  Scopes: {user_info['scopes']}")

    # --- Build config dict ---
    config_data: dict = {"github_token": resolved_token}

    if prompt_file:
        pf = Path(prompt_file).expanduser()
        if not pf.is_file():
            click.echo(f"[WARN] Prompt file not found: {pf}. Saving path anyway.")
        config_data["prompt_file"] = str(pf)

    if ai_provider:
        config_data["ai_provider"] = ai_provider
    if ai_model:
        config_data["ai_model"] = ai_model
    if ai_api_key:
        config_data["ai_api_key"] = ai_api_key

    # --- Write ~/.sdlc/config.yml ---
    _USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if _USER_CONFIG_PATH.is_file():
        # Merge into existing YAML config.
        import yaml

        existing: dict = {}
        try:
            with open(_USER_CONFIG_PATH, encoding="utf-8") as fh:
                raw = yaml.safe_load(fh)
                existing = raw if isinstance(raw, dict) else {}
        except (OSError, yaml.YAMLError):
            pass

        sdlc_section = existing.get("sdlc", {})
        if not isinstance(sdlc_section, dict):
            sdlc_section = {}
        sdlc_section.update(config_data)
        existing["sdlc"] = sdlc_section

        with open(_USER_CONFIG_PATH, "w", encoding="utf-8") as fh:
            yaml.dump(existing, fh, default_flow_style=False, sort_keys=False)
        _restrict_file_permissions(_USER_CONFIG_PATH)
    else:
        # First run — write a fully-commented template with user values filled in.
        _USER_CONFIG_PATH.write_text(
            _build_user_config_template(config_data), encoding="utf-8",
        )
        _restrict_file_permissions(_USER_CONFIG_PATH)

    click.echo(f"✓ Config written to {_USER_CONFIG_PATH}")
