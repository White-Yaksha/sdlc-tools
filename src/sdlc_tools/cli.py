"""CLI entry point — ``sdlc-tools`` command with subcommands."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
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
# review
# -----------------------------------------------------------------------


@main.command()
@click.option("--base-branch", default=None, help="Base branch for diff (overrides config).")
@click.option("--provider", "ai_provider", default=None,
              help="AI provider: copilot, openai, anthropic, gemini, ollama.")
@click.option("--model", "ai_model", default=None, help="AI model name (overrides config).")
@click.option("--push", "push_first", is_flag=True, default=False,
              help="Push the current branch to origin before generating the review.")
@click.option("--force-push", "force_push", is_flag=True, default=False,
              help="Force-push the current branch (implies --push).")
@click.option(
    "--persona",
    "personas",
    multiple=True,
    help="Reviewer persona. Repeat for multiple; use 'all' for all personas. "
         "If omitted, primary persona is used.",
)
@click.pass_context
def review(
    ctx: click.Context,
    base_branch: str | None,
    ai_provider: str | None,
    ai_model: str | None,
    push_first: bool,
    force_push: bool,
    personas: tuple[str, ...],
) -> None:
    """Generate an AI review report (persona-based) and post it to the PR."""
    from sdlc_tools.client import GitHubClient
    from sdlc_tools.report import ReportGenerator

    if push_first or force_push:
        from sdlc_tools.git import push_current_branch

        if not push_current_branch(force=force_push):
            click.echo("[ERROR] Git push failed. Aborting review.", err=True)
            sys.exit(1)

    config = _build_config(ctx, {
        "base_branch": base_branch,
        "ai_provider": ai_provider,
        "ai_model": ai_model,
    })
    _log_config(config, "review")

    try:
        client = GitHubClient(token=config.github_token, dry_run=config.dry_run)
    except ValueError as exc:
        click.echo(f"[ERROR] {exc}", err=True)
        sys.exit(1)

    generator = ReportGenerator(client, config)
    generator.review(personas=list(personas))


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

def _build_project_config_template(values: dict) -> str:
    """Build a commented ``.sdlc.yml`` template with safe project-level defaults."""
    repo = str(values.get("github_repository", "")).strip()
    repo_line = f"  github_repository: {repo}" if repo else "  # github_repository: owner/repo"

    return (
        "# SDLC Tools — Project Configuration\n"
        "# This file contains project-specific settings (committed to git).\n"
        "# User-level secrets (github_token, ai_api_key) belong in ~/.sdlc/config.yml\n"
        "# or environment variables.\n"
        "# (run: sdlc-tools setup)\n"
        "#\n"
        "# Config precedence (lowest → highest):\n"
        "#   code defaults → ~/.sdlc/config.yml → .sdlc.yml → env vars → CLI args\n"
        "#\n"
        "# See: https://github.com/White-Yaksha/sdlc-tools\n"
        "\n"
        "sdlc:\n"
        "  # ── Branch & Release ──────────────────────────────────────\n"
        "  # base_branch: develop              # Branch to diff against\n"
        "  # release_prefix: releases          # PR branch prefix for auto-tagging\n"
        "  # release_tag_name: vYYYY.M-N       # Tag created by `sdlc-tools tag`\n"
        "\n"
        "  # ── GitHub Runtime Context ───────────────────────────────\n"
        + repo_line + "\n"
        "  # github_event_name: pull_request   # Local tag testing only; "
        "auto-set in GitHub Actions\n"
        "  # github_event_path: \"C:\\path\\to\\event.json\"  # Local tag testing only\n"
        "\n"
        "  # ── Report Settings ───────────────────────────────────────\n"
        "  # max_diff_length: 20000            # Truncate diff beyond this (chars)\n"
        "  # comment_marker: \"<!-- AI-SDLC-REPORT -->\"  "
        "# HTML marker for idempotent PR comments\n"
        "  # review_comment_marker: \"<!-- AI-SDLC-REVIEW -->\"\n"
        "\n"
        "  # ── AI Provider ───────────────────────────────────────────\n"
        "  # ai_provider: copilot              # copilot & ollama: "
        "local only; CI: openai|anthropic|gemini\n"
        "  # ai_model: \"\"                      # Model name (provider default if empty)\n"
        "  # ai_base_url: \"\"                   # Custom endpoint / proxy URL\n"
        "  # ai_timeout: 120                   # Request timeout in seconds\n"
        "\n"
        "  # ── Prompt ────────────────────────────────────────────────\n"
        "  # prompt_file: \"\"                   # Path to custom prompt "
        "(empty → bundled default)\n"
        "  # instruction_root: \"instructions\"  # Base directory for "
        "report/review instruction markdown\n"
        "  # risk_rules_file: \"config/risk_rules.yaml\"\n"
        "  # review_personas_file: \"config/review_personas.yaml\"\n"
        "\n"
        "  # ── Behaviour ─────────────────────────────────────────────\n"
        "  # dry_run: false                    # Preview without side effects\n"
        "  # verbose: false                    # Enable debug logging\n"
        "  # log_file: \"\"                      # Write logs to file\n"
    )

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

_INIT_FILE_TEMPLATES: dict[str, str] = {
    "config/risk_rules.yaml": """\
high_risk_paths:
  - database/
  - migrations/
  - auth/

file_type_rules:
  ".sql": "database schema change"
  ".yaml": "config modification"

dependency_files:
  - requirements.txt
  - package.json
  - pyproject.toml

patterns:
  - name: schema_change
    regex: ALTER TABLE|CREATE TABLE|DROP TABLE
  - name: retry_logic
    regex: retry|backoff|timeout
""",
    "config/review_personas.yaml": """\
primary_persona: security
personas:
  security: instructions/review/personas/security.md
  performance: instructions/review/personas/performance.md
  architecture: instructions/review/personas/architecture.md
""",
    "instructions/report/report_base.md": """\
# Report Mode

You are generating a pull request change impact report for the PR author.
Focus on:
- high-level summary of what changed
- potential risks and affected components
- rollout/compatibility considerations
- test and validation impact

Be concise, structured, and actionable.
""",
    "instructions/review/review_base.md": """\
# Review Mode

You are generating reviewer feedback for a pull request.
Focus on:
- correctness and logic risks
- security/stability/performance concerns
- missing tests and failure scenarios
- concrete recommendations

Return clear, prioritized, reviewer-ready feedback.
""",
    "instructions/review/personas/security.md": """\
Prioritize security concerns:
- authN/authZ boundaries
- secrets handling
- injection vectors and input validation
- privilege escalation and data exposure
""",
    "instructions/review/personas/performance.md": """\
Prioritize performance concerns:
- unnecessary repeated work
- expensive I/O or queries
- memory and CPU hotspots
- scalability implications under load
""",
    "instructions/review/personas/architecture.md": """\
Prioritize architecture concerns:
- layering and boundaries
- coupling and cohesion
- extensibility and maintainability
- consistency with existing patterns
""",
    "event.json": """\
{
  "action": "closed",
  "pull_request": {
    "merged": true,
    "base": {
      "ref": "releases/2026.3"
    }
  }
}
""",
}

_INIT_MANDATORY_PATHS: tuple[str, ...] = (
    "instructions/report/report_base.md",
    "instructions/review/review_base.md",
)

_INIT_OPTIONAL_BUNDLES: dict[str, tuple[str, ...]] = {
    "risk-rules": ("config/risk_rules.yaml",),
    "review-personas": (
        "config/review_personas.yaml",
        "instructions/review/personas/security.md",
        "instructions/review/personas/performance.md",
        "instructions/review/personas/architecture.md",
    ),
    "ai-report-workflow": (".github/workflows/ai-report.yml",),
    "release-tag-workflow": (".github/workflows/release-tag.yml",),
    "local-tag-event-json": ("event.json",),
}

_INIT_WORKFLOW_BUNDLES: set[str] = {"ai-report-workflow", "release-tag-workflow"}
_INIT_OPTIONAL_SELECTION_CHOICES: tuple[str, ...] = (
    *tuple(_INIT_OPTIONAL_BUNDLES),
    "select-all",
    "all",
    "select-none",
    "none",
)
_INIT_OPTIONAL_BUNDLE_DESCRIPTIONS: dict[str, str] = {
    "risk-rules": "config/risk_rules.yaml",
    "review-personas": "config/review_personas.yaml + persona templates",
    "ai-report-workflow": ".github/workflows/ai-report.yml",
    "release-tag-workflow": ".github/workflows/release-tag.yml",
    "local-tag-event-json": "event.json for local tag testing",
}
_INIT_TEMPLATE_CONTENTS: dict[str, str] = {
    **_INIT_FILE_TEMPLATES,
    ".github/workflows/ai-report.yml": _WORKFLOW_TEMPLATES["ai-report.yml"],
    ".github/workflows/release-tag.yml": _WORKFLOW_TEMPLATES["release-tag.yml"],
}


def _is_interactive_terminal() -> bool:
    """Return True when stdin/stdout are connected to an interactive TTY."""
    stdin = click.get_text_stream("stdin")
    stdout = click.get_text_stream("stdout")
    stdin_tty = bool(getattr(stdin, "isatty", lambda: False)())
    stdout_tty = bool(getattr(stdout, "isatty", lambda: False)())
    return stdin_tty and stdout_tty


def _parse_optional_bundle_selection(values: tuple[str, ...]) -> list[str]:
    """Parse and validate optional bundle selections."""
    tokens = [v.strip().lower() for v in values if v.strip()]
    if not tokens:
        return []

    has_select_all = any(v in {"select-all", "all"} for v in tokens)
    has_select_none = any(v in {"select-none", "none"} for v in tokens)
    if has_select_all and has_select_none:
        raise click.BadParameter(
            "Cannot combine select-all/all with select-none/none for --optional.",
            param_hint="--optional",
        )
    if has_select_all:
        return list(_INIT_OPTIONAL_BUNDLES)
    if has_select_none:
        return []

    supported = set(_INIT_OPTIONAL_BUNDLES)
    unknown = [v for v in tokens if v not in supported]
    if unknown:
        choices = ", ".join(_INIT_OPTIONAL_SELECTION_CHOICES)
        raise click.BadParameter(
            f"Unknown optional bundle(s): {', '.join(unknown)}. Use one of: {choices}",
            param_hint="--optional",
        )

    selected: list[str] = []
    for token in tokens:
        if token not in selected:
            selected.append(token)
    return selected


def _read_navigation_key(*, key_reader: Callable[[], str]) -> str:
    """Read one navigation key event from terminal input."""
    key = str(key_reader())

    if key in ("\r", "\n"):
        return "enter"
    if key in ("\x1b[A", "\x1bOA"):
        return "up"
    if key in ("\x1b[B", "\x1bOB"):
        return "down"
    # Some Windows terminals return combined two-char codes (e.g. "\xe0P").
    if len(key) == 2 and key[0] in ("\x00", "\xe0"):
        if key[1] == "H":
            return "up"
        if key[1] == "P":
            return "down"
        return "other"

    # Windows arrow keys often arrive as a two-character sequence.
    if key in ("\x00", "\xe0"):
        follow = str(key_reader())
        if follow == "H":
            return "up"
        if follow == "P":
            return "down"
        return "other"

    # POSIX terminals may emit ESC + [ + A/B.
    if key == "\x1b":
        second = str(key_reader())
        if second in ("[", "O"):
            third = str(key_reader())
            if third == "A":
                return "up"
            if third == "B":
                return "down"
        return "other"

    if key.lower() in {"k", "w"}:
        return "up"
    if key.lower() in {"j", "s"}:
        return "down"
    return "other"


def _supports_ansi_redraw() -> bool:
    """Return True when stdout is likely to support ANSI redraw sequences."""
    stream = click.get_text_stream("stdout")
    return bool(getattr(stream, "isatty", lambda: False)())


def _render_optional_mode_menu(
    *,
    modes: list[tuple[str, str]],
    index: int,
    previous_lines: int,
    use_ansi_redraw: bool,
) -> int:
    """Render the optional-mode menu with the current item highlighted."""
    if use_ansi_redraw and previous_lines > 0:
        click.echo(f"\x1b[{previous_lines}A", nl=False)

    rendered_lines = 0
    for i, (_, label) in enumerate(modes):
        prefix = ">" if i == index else " "
        line = f"{prefix} {label}"
        if i == index:
            line = click.style(line, reverse=True)
        if use_ansi_redraw:
            click.echo(f"\x1b[2K{line}")
        else:
            click.echo(line)
        rendered_lines += 1
    return rendered_lines


def _prompt_optional_mode_with_arrows(
    *,
    key_reader: Callable[[], str] | None = None,
) -> str:
    """Prompt for optional selection mode using arrow keys + Enter."""
    reader = key_reader or click.getchar
    modes: list[tuple[str, str]] = [
        ("select-all", "Select all optional bundles"),
        ("select-none", "Select none (mandatory files only)"),
        ("custom", "Custom per-bundle selection (y/N prompts)"),
    ]

    index = 0
    use_ansi_redraw = _supports_ansi_redraw()
    rendered_lines = 0
    click.echo("\nChoose optional selection mode (↑/↓ + Enter):")
    rendered_lines = _render_optional_mode_menu(
        modes=modes,
        index=index,
        previous_lines=rendered_lines,
        use_ansi_redraw=use_ansi_redraw,
    )

    while True:
        nav = _read_navigation_key(key_reader=reader)
        if nav == "up":
            index = (index - 1) % len(modes)
            rendered_lines = _render_optional_mode_menu(
                modes=modes,
                index=index,
                previous_lines=rendered_lines,
                use_ansi_redraw=use_ansi_redraw,
            )
            continue
        if nav == "down":
            index = (index + 1) % len(modes)
            rendered_lines = _render_optional_mode_menu(
                modes=modes,
                index=index,
                previous_lines=rendered_lines,
                use_ansi_redraw=use_ansi_redraw,
            )
            continue
        if nav == "enter":
            click.echo(f"Selected: {modes[index][1]}")
            return modes[index][0]


def _prompt_custom_optional_bundles() -> list[str]:
    """Prompt y/N for each optional init bundle."""
    click.echo("\nCustom optional bundle selection (y/N):")
    selected: list[str] = []
    for key, description in _INIT_OPTIONAL_BUNDLE_DESCRIPTIONS.items():
        include = click.confirm(
            f"Include {key} ({description})?",
            default=False,
            show_default=True,
        )
        if include:
            selected.append(key)
    return selected


def _prompt_optional_bundle_selection() -> list[str]:
    """Interactive optional-bundle selector for init command."""
    mode = _prompt_optional_mode_with_arrows()
    if mode == "select-all":
        return list(_INIT_OPTIONAL_BUNDLES)
    if mode == "select-none":
        return []
    return _prompt_custom_optional_bundles()


def _resolve_optional_bundles(
    *,
    optional_bundles: tuple[str, ...],
    skip_workflows: bool,
) -> list[str]:
    """Resolve optional init bundle selection from CLI or interactive input."""
    if optional_bundles:
        selected = _parse_optional_bundle_selection(optional_bundles)
    elif _is_interactive_terminal():
        selected = _prompt_optional_bundle_selection()
    else:
        selected = list(_INIT_OPTIONAL_BUNDLES)

    if skip_workflows:
        filtered = [bundle for bundle in selected if bundle not in _INIT_WORKFLOW_BUNDLES]
        if len(filtered) != len(selected):
            click.echo("[INFO] --skip-workflows is set; workflow bundles were excluded.")
        selected = filtered

    return selected


def _scaffold_template_file(rel_path: str, created: list[str]) -> None:
    """Create a scaffold file when missing; skip when it already exists."""
    target = Path.cwd() / Path(rel_path)
    if target.exists():
        click.echo(f"  skip  {rel_path} (already exists)")
        return

    content = _INIT_TEMPLATE_CONTENTS[rel_path]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    created.append(str(target))
    click.echo(f"  create  {rel_path}")


# -----------------------------------------------------------------------
# init
# -----------------------------------------------------------------------


@main.command()
@click.option(
    "--optional",
    "optional_bundles",
    multiple=True,
    type=click.Choice(_INIT_OPTIONAL_SELECTION_CHOICES, case_sensitive=False),
    help=(
        "Optional scaffold bundle to include (repeatable). "
        "Use select-all/all or select-none/none."
    ),
)
@click.option(
    "--skip-workflows", is_flag=True, default=False,
    help="Skip generating GitHub Actions workflow files.",
)
@click.pass_context
def init(
    ctx: click.Context,
    optional_bundles: tuple[str, ...],
    skip_workflows: bool,
) -> None:
    """Create .sdlc.yml, analysis templates, and optional workflow files."""
    from sdlc_tools.git import get_repo_url

    created: list[str] = []

    # --- .sdlc.yml ---
    sdlc_yml = Path.cwd() / ".sdlc.yml"
    if sdlc_yml.exists():
        click.echo("  skip  .sdlc.yml (already exists)")
    else:
        template_values = {"github_repository": get_repo_url()}
        sdlc_yml.write_text(_build_project_config_template(template_values), encoding="utf-8")
        created.append(str(sdlc_yml))
        click.echo(f"  create  {sdlc_yml}")

    # --- mandatory analysis templates ---
    for rel_path in _INIT_MANDATORY_PATHS:
        _scaffold_template_file(rel_path, created)

    # --- optional bundles ---
    selected_optional_bundles = _resolve_optional_bundles(
        optional_bundles=optional_bundles,
        skip_workflows=skip_workflows,
    )
    if selected_optional_bundles:
        click.echo(f"[INFO] Optional bundles: {', '.join(selected_optional_bundles)}")
    else:
        click.echo("[INFO] Optional bundles: none")

    selected_paths: list[str] = []
    for bundle in selected_optional_bundles:
        selected_paths.extend(_INIT_OPTIONAL_BUNDLES[bundle])
    for rel_path in dict.fromkeys(selected_paths):
        _scaffold_template_file(rel_path, created)

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
        '  # review_comment_marker: "<!-- AI-SDLC-REVIEW -->"\n'
        "\n"
        "  # ── Instruction & Analyzer Files ─────────────────────\n"
        '  # instruction_root: "instructions"\n'
        '  # risk_rules_file: "config/risk_rules.yaml"\n'
        '  # review_personas_file: "config/review_personas.yaml"\n'
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
