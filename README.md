# sdlc-tools

> A pip-installable Python CLI toolkit for SDLC automation — AI code impact reports, release tagging, and PR management.

[![CI](https://github.com/White-Yaksha/sdlc-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/White-Yaksha/sdlc-tools/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## What It Does

| Command | Description |
|---|---|
| `sdlc-tools report` | Generates an AI code impact report using your chosen provider and posts it as a styled HTML comment on the PR. |
| `sdlc-tools tag` | Creates or updates a release tag when a PR is merged into a release branch (designed for GitHub Actions). |
| `sdlc-tools setup` | Validates your GitHub token, configures your AI provider, and writes everything to `~/.sdlc/config.yml`. |
| `sdlc-tools init` | Scaffolds `.sdlc.yml` config + GitHub Actions workflows (`ai-report.yml`, `release-tag.yml`) in the current repo. |

---

## Quick Start

### 1. Install

```bash
pip install git+https://github.com/White-Yaksha/sdlc-tools.git
```

Or pin a version:

```bash
pip install git+https://github.com/White-Yaksha/sdlc-tools.git@v0.1.0
```

> **Note:** If `sdlc-tools` isn't found after install, use `python -m sdlc_tools` instead, or add Python's `Scripts` directory to your PATH.
>
> All commands work with either invocation:
> ```bash
> sdlc-tools report          # if Scripts is on PATH
> python -m sdlc_tools report  # always works
> ```

### 2. Set up your token and AI provider

```bash
sdlc-tools setup
# or: python -m sdlc_tools setup
```

This validates your GitHub token (from `GITHUB_TOKEN` env var or prompts you), checks it against the GitHub API, and saves it to `~/.sdlc/config.yml`.

Configure your AI provider at the same time:

```bash
# Free option — Gemini (Google AI, free tier available)
sdlc-tools setup --provider gemini --ai-key AIza-your-key

# Free option — Ollama (fully local, no API key needed)
sdlc-tools setup --provider ollama

# Paid option — OpenAI
sdlc-tools setup --provider openai --ai-key sk-your-key

# Default — GitHub Copilot CLI (requires Copilot subscription + gh CLI installed)
sdlc-tools setup
```

### 3. Initialize project config + workflows

```bash
cd your-repo
sdlc-tools init
# or: python -m sdlc_tools init
```

This creates **three files** (skipping any that already exist):

| File | Purpose |
|---|---|
| `.sdlc.yml` | Project-level settings (committed to git) |
| `.github/workflows/ai-report.yml` | AI code impact report on every PR |
| `.github/workflows/release-tag.yml` | Auto-tag on PR merge into `releases/**` |

Edit `.sdlc.yml` to match your project:

```yaml
sdlc:
  base_branch: develop
  # release_prefix: releases
  # max_diff_length: 20000
```

To skip workflow generation (config only):

```bash
sdlc-tools init --skip-workflows
```

### 4. Use it

```bash
# Generate AI report and post to PR
sdlc-tools report
# or: python -m sdlc_tools report

# Preview without side effects
sdlc-tools report --dry-run

# Override provider/model at runtime
sdlc-tools report --provider anthropic --model claude-sonnet-4-20250514

# Verbose output
sdlc-tools report -v
```

---

## Multi-Model AI Support

sdlc-tools supports **5 AI providers** out of the box. Choose the one that fits your workflow and budget:

| Provider | Default Model | API Key Env Var | Free? |
|---|---|---|---|
| `copilot` (default) | — (uses `gh copilot` CLI) | Copilot subscription + [GitHub CLI](https://cli.github.com) | ✗ |
| `openai` | `gpt-4o` | `OPENAI_API_KEY` | ✗ |
| `anthropic` | `claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` | ✗ |
| `gemini` | `gemini-2.0-flash` | `GEMINI_API_KEY` | ✓ (free tier) |
| `ollama` | `llama3.2` | **None needed** | ✓ (fully local) |

### API Key Resolution Order

1. `ai_api_key` in config (CLI arg → `AI_API_KEY` env var → config file)
2. Provider-specific env var (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`)
3. If neither is found → error (except `copilot` and `ollama`, which need no key)

### Custom Endpoints

All HTTP-based providers support `ai_base_url` for proxies, self-hosted models, or Azure OpenAI:

```yaml
sdlc:
  ai_provider: openai
  ai_base_url: https://my-proxy.example.com
```

---

## CLI Reference

Both `sdlc-tools` and `python -m sdlc_tools` are equivalent. All examples below use the short form.

```
Usage: sdlc-tools [OPTIONS] COMMAND [ARGS]...

Options:
  --dry-run        Preview actions without side effects.
  -v, --verbose    Enable debug logging.
  --config PATH    Path to .sdlc.yml config file.
  --log-file TEXT   Write logs to a file.
  --version        Show version and exit.
  -h, --help       Show this message and exit.

Commands:
  init    Create a .sdlc.yml project config file.
  report  Generate an AI code impact report and post to PR.
  setup   Set up user-level config at ~/.sdlc/config.yml.
  tag     Create or update a release tag (CI workflow).
```

### `sdlc-tools report`

| Option | Description |
|---|---|
| `--base-branch TEXT` | Base branch for diff (overrides config). |
| `--provider TEXT` | AI provider: `copilot`, `openai`, `anthropic`, `gemini`, `ollama`. |
| `--model TEXT` | AI model name (overrides config default). |

**How it works:** Generates a `git diff` against the base branch → sends it to the configured AI provider with the prompt template → converts the Markdown response to styled HTML → posts it as an idempotent comment on the open PR (or creates a draft PR if none exists).

### `sdlc-tools tag`

| Option | Description |
|---|---|
| `--tag-name TEXT` | Tag name to create (overrides config). |
| `--event-path TEXT` | Path to GitHub event JSON (CI only). |

**How it works:** Reads the GitHub Actions PR event payload → checks if the PR was merged into a release branch (matching `release_prefix`) → creates/updates a lightweight tag. Idempotent — safe to re-run.

### `sdlc-tools setup`

| Option | Description |
|---|---|
| `--token TEXT` | GitHub personal access token. |
| `--prompt-file TEXT` | Path to a custom AI prompt file. |
| `--provider TEXT` | AI provider: `copilot`, `openai`, `anthropic`, `gemini`, `ollama`. |
| `--model TEXT` | Default AI model name. |
| `--ai-key TEXT` | API key for the AI provider. |

**How it works:** Auto-detects or prompts for a GitHub token → validates it against the GitHub API (shows username + scopes) → writes all settings to `~/.sdlc/config.yml`. Merges with existing config if present.

### `sdlc-tools init`

Scaffolds project config and CI workflows:

```
sdlc-tools init                 # creates .sdlc.yml + .github/workflows/{ai-report,release-tag}.yml
sdlc-tools init --skip-workflows  # creates .sdlc.yml only
```

Existing files are never overwritten — safe to re-run.

---

## Configuration

Configuration is resolved in **five layers** (lowest → highest priority):

```
Code defaults → ~/.sdlc/config.yml → .sdlc.yml → Environment variables → CLI arguments
```

### `~/.sdlc/config.yml` — User Global

Created by `sdlc-tools setup`. Not committed to git — personal to each developer:

```yaml
sdlc:
  github_token: ghp_your_token_here
  ai_provider: openai
  ai_model: gpt-4o
  ai_api_key: sk-...
  prompt_file: ~/prompts/my-custom-prompt.txt
```

### `.sdlc.yml` — Project Level

Created by `sdlc-tools init`. Committed to git — shared across the team:

```yaml
sdlc:
  base_branch: develop
  release_prefix: releases
  max_diff_length: 20000
  comment_marker: "<!-- AI-SDLC-REPORT -->"
```

### All Config Fields

| Field | Default | Description |
|---|---|---|
| `base_branch` | `develop` | Branch to diff against |
| `release_prefix` | `releases` | Prefix for release branch detection |
| `release_tag_name` | — | Tag name to create on merge |
| `max_diff_length` | `20000` | Max diff characters sent to AI |
| `comment_marker` | `<!-- AI-SDLC-REPORT -->` | HTML marker for idempotent PR comments |
| `github_token` | — | GitHub PAT (auto-detected or prompted) |
| `prompt_file` | — | Custom prompt file path (falls back to built-in) |
| `ai_provider` | `copilot` | AI backend (`copilot`/`openai`/`anthropic`/`gemini`/`ollama`) |
| `ai_model` | — | Override provider's default model |
| `ai_api_key` | — | API key (or use provider-specific env var) |
| `ai_base_url` | — | Custom API endpoint for proxies |
| `ai_timeout` | `120` | API call timeout in seconds |

### Environment Variables

| Variable | Maps to |
|---|---|
| `GITHUB_TOKEN` | `github_token` |
| `GITHUB_REPOSITORY` | `github_repository` |
| `GITHUB_EVENT_NAME` | `github_event_name` |
| `GITHUB_EVENT_PATH` | `github_event_path` |
| `BASE_BRANCH` | `base_branch` |
| `RELEASE_PREFIX` | `release_prefix` |
| `RELEASE_TAG_NAME` | `release_tag_name` |
| `MAX_DIFF_LENGTH` | `max_diff_length` |
| `COMMENT_MARKER` | `comment_marker` |
| `DRY_RUN` | `dry_run` |
| `AI_PROVIDER` | `ai_provider` |
| `AI_MODEL` | `ai_model` |
| `AI_API_KEY` | `ai_api_key` |
| `AI_BASE_URL` | `ai_base_url` |
| `AI_TIMEOUT` | `ai_timeout` |

---

## Custom Prompt

By default, sdlc-tools uses a built-in prompt that analyzes diffs across 6 dimensions: high-level summary, impacted components, risk assessment, database impact, configuration impact, and backward compatibility.

Override it with your own:

```bash
sdlc-tools setup --prompt-file ~/prompts/security-review.txt
```

Or in `~/.sdlc/config.yml`:

```yaml
sdlc:
  prompt_file: ~/prompts/security-review.txt
```

Example custom prompt:

```text
You are a security-focused code reviewer.
Analyze this diff for vulnerabilities, auth issues, and data leaks.
Classify risk as Low / Medium / High / Critical.
Here is the git diff:
```

If the file is missing at runtime, the tool falls back to the bundled default.

---

## GitHub Actions Usage

> **Tip:** `sdlc-tools init` generates both workflow files below automatically. You only need to add your provider's API key as a repository secret.

### AI Report on Pull Requests

```yaml
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
          AI_PROVIDER: gemini   # or: openai, anthropic, ollama, copilot
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
```

### Release Tagging on PR Merge

```yaml
name: Release Tag
on:
  pull_request:
    types: [closed]
    branches:
      - 'releases/**'

jobs:
  tag:
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
```

---

## Pre-Push Hook

Automatically generate AI reports before pushing:

```bash
cat > .git/hooks/pre-push << 'EOF'
#!/bin/sh
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "develop" ] && ! echo "$BRANCH" | grep -q "^release"; then
    echo "[SDLC] Running AI report..."
    sdlc-tools report &
    disown
fi
exit 0
EOF
chmod +x .git/hooks/pre-push
```

---

## Architecture

```
sdlc-tools/
├── src/sdlc_tools/
│   ├── cli.py               ← Click CLI (report, tag, setup, init)
│   ├── config.py            ← 5-layer config system (dataclass + YAML + env)
│   ├── ai.py                ← AI provider abstraction (5 providers + factory)
│   ├── report.py            ← Report orchestrator (diff → AI → HTML → PR)
│   ├── client.py            ← GitHub REST API client (auth, PRs, comments, tags)
│   ├── git.py               ← Git operations (diff, branch, fetch)
│   ├── html.py              ← Markdown → styled HTML converter
│   ├── tagger.py            ← Release tag manager (event-driven)
│   ├── log.py               ← Structured logging setup
│   └── prompts/
│       ├── __init__.py      ← Prompt loader (custom file or bundled default)
│       └── default.txt      ← Built-in analysis prompt (6-section template)
```

### Report Flow

```
sdlc-tools report
  │
  ├─ config.py      → Load 5-layer config
  ├─ git.py         → git diff origin/<base>...HEAD
  ├─ prompts/       → Load prompt template
  ├─ ai.py          → Send to AI provider (OpenAI/Gemini/Ollama/etc.)
  ├─ html.py        → Convert Markdown response → styled HTML
  └─ client.py      → POST/PATCH comment on PR (idempotent via marker)
```

### Key Design Decisions

- **No new dependencies for AI** — all providers use the existing `requests` library
- **Idempotent operations** — PR comments update in place (no duplicates), tags delete-before-create
- **Dry-run at every layer** — `--dry-run` skips all write operations (AI calls, API posts)
- **Provider abstraction** — `AIProvider` ABC with `analyze(prompt, diff) → str` makes adding new providers trivial

---

## Development

```bash
git clone https://github.com/White-Yaksha/sdlc-tools.git
cd sdlc-tools

# Install in editable mode with dev deps
pip install -e ".[dev]"

# Lint
ruff check src/ tests/

# Test (70 tests)
pytest --tb=short -q

# Coverage (80% threshold)
coverage run -m pytest && coverage report --fail-under=80
```

### Dependencies

| Package | Purpose |
|---|---|
| `click >=8.1` | CLI framework |
| `requests >=2.31` | HTTP client (GitHub API + AI providers) |
| `pyyaml >=6.0` | YAML config parsing |
| `pytest`, `responses`, `ruff` | Dev: testing, HTTP mocking, linting |

**No external CLI tools required.** The only exception is the `copilot` AI provider, which requires the [GitHub CLI](https://cli.github.com) (`gh`) to be installed. All other providers (gemini, openai, anthropic, ollama) work with zero external dependencies.

---

## License

MIT — see [LICENSE](LICENSE).
