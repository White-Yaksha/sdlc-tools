"""CLI entry point — ``sdlc-tools`` command with subcommands."""

from __future__ import annotations

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


# -----------------------------------------------------------------------
# report
# -----------------------------------------------------------------------


@main.command()
@click.option("--base-branch", default=None, help="Base branch for diff (overrides config).")
@click.option("--provider", "ai_provider", default=None,
              help="AI provider: copilot, openai, anthropic, gemini, ollama.")
@click.option("--model", "ai_model", default=None, help="AI model name (overrides config).")
@click.pass_context
def report(
    ctx: click.Context,
    base_branch: str | None,
    ai_provider: str | None,
    ai_model: str | None,
) -> None:
    """Generate an AI code impact report and post it to the PR."""
    from sdlc_tools.client import GitHubClient
    from sdlc_tools.report import ReportGenerator

    config = _build_config(ctx, {
        "base_branch": base_branch,
        "ai_provider": ai_provider,
        "ai_model": ai_model,
    })

    try:
        client = GitHubClient(token=config.github_token, dry_run=config.dry_run)
    except ValueError as exc:
        click.echo(f"[ERROR] {exc}", err=True)
        sys.exit(1)

    generator = ReportGenerator(client, config)
    generator.run()


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
# This file contains project-specific settings. User-level settings
# (token, custom prompt) live in ~/.sdlc/config.yml (run: sdlc-tools setup).
#
# Config precedence (lowest → highest):
#   code defaults → ~/.sdlc/config.yml → .sdlc.yml → env vars → CLI args
#
# See: https://github.com/White-Yaksha/sdlc-tools
sdlc:
  # base_branch: develop
  # release_prefix: releases
  # max_diff_length: 20000
  # comment_marker: "<!-- AI-SDLC-REPORT -->"
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
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - run: pip install git+https://github.com/White-Yaksha/sdlc-tools.git

      - run: sdlc-tools report --base-branch ${{ github.base_ref }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          # Choose your AI provider and set the matching secret.
          # Supported: copilot, openai, anthropic, gemini, ollama
          AI_PROVIDER: gemini
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          # For OpenAI:     AI_PROVIDER: openai   + OPENAI_API_KEY
          # For Anthropic:  AI_PROVIDER: anthropic + ANTHROPIC_API_KEY
          # For Copilot:    AI_PROVIDER: copilot   (uses gh CLI auth)
          # For Ollama:     AI_PROVIDER: ollama    (needs self-hosted runner)
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

    import yaml

    existing: dict = {}
    if _USER_CONFIG_PATH.is_file():
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

    click.echo(f"✓ Config written to {_USER_CONFIG_PATH}")
