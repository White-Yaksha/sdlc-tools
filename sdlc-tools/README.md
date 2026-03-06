# sdlc-tools

> A pip-installable Python CLI toolkit for SDLC automation — AI code impact reports, release tagging, and PR management.

[![CI](https://github.com/White-Yaksha/sdlc-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/White-Yaksha/sdlc-tools/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## What It Does

| Command | Description |
|---|---|
| `sdlc-tools report` | Generates an AI code impact report (via configurable AI provider) and posts it as a styled HTML comment on the associated PR. |
| `sdlc-tools tag` | Creates or updates a release tag when a PR is merged into a release branch (designed for GitHub Actions). |
| `sdlc-tools setup` | Validates your GitHub token and writes user-level config to `~/.sdlc/config.yml`. |
| `sdlc-tools init` | Scaffolds a `.sdlc.yml` project config file in the current repository. |

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

### 2. Set up your token

```bash
sdlc-tools setup
```

This auto-detects your GitHub token (from `gh auth token` or prompts you), validates it, and saves it to `~/.sdlc/config.yml`. Optionally set a custom AI prompt or provider:

```bash
sdlc-tools setup --prompt-file ~/my-custom-prompt.txt
```

```bash
# Use OpenAI instead of the default Copilot CLI
sdlc-tools setup --provider openai --ai-key sk-your-key-here
```

### 3. Initialize project config

```bash
cd your-repo
sdlc-tools init
```

This creates a `.sdlc.yml` file with project-level settings (committed to git):

```yaml
sdlc:
  base_branch: releases/2026.3
  release_prefix: releases
  max_diff_length: 20000
```

### 4. Use it

```bash
# Generate AI report and post to PR
sdlc-tools report

# Preview without side effects
sdlc-tools report --dry-run

# Verbose output
sdlc-tools report -v
```

---

## CLI Reference

```
Usage: sdlc-tools [OPTIONS] COMMAND [ARGS]...

  SDLC Tools — A developer CLI for SDLC automation.

Options:
  --dry-run       Preview actions without side effects.
  -v, --verbose   Enable debug logging.
  --config PATH   Path to .sdlc.yml config file.
  --log-file TEXT  Write logs to a file.
  --version       Show version and exit.
  -h, --help      Show this message and exit.

Commands:
  init    Create a .sdlc.yml project config file in the current directory.
  report  Generate an AI code impact report and post it to the PR.
  setup   Set up user-level config at ~/.sdlc/config.yml (token + prompt).
  tag     Create or update a release tag (CI workflow command).
```

### `sdlc-tools report`

```
Options:
  --base-branch TEXT  Base branch for diff (overrides config).
  --provider TEXT     AI provider: copilot, openai, anthropic, gemini, ollama.
  --model TEXT        AI model name (overrides config).
```

Generates a git diff against the base branch, sends it to the configured AI provider for analysis, converts the Markdown response to styled HTML, and posts it as a comment on the open PR (or creates a draft PR if none exists).

### `sdlc-tools tag`

```
Options:
  --tag-name TEXT    Tag name to create (overrides config).
  --event-path TEXT  Path to GitHub event JSON (CI only).
```

Designed for GitHub Actions. Reads the PR event payload, checks if the PR was merged into a release branch, and creates/updates a lightweight tag.

### `sdlc-tools setup`

```
Options:
  --token TEXT        GitHub personal access token.
  --prompt-file TEXT  Path to a custom Copilot prompt file.
  --provider TEXT     AI provider: copilot, openai, anthropic, gemini, ollama.
  --model TEXT        Default AI model name.
  --ai-key TEXT       API key for the AI provider.
```

Validates your GitHub token against the API, then writes user-level config to `~/.sdlc/config.yml`. Auto-detects tokens from `gh auth token` if not provided.

---

## Configuration

Configuration is resolved in five layers (lowest → highest priority):

1. **Code defaults** — built into the tool
2. **`~/.sdlc/config.yml`** — user-level global config (token, prompt, personal prefs)
3. **`.sdlc.yml`** file in the repo root — project-level settings
4. **Environment variables** (for CI)
5. **CLI arguments** (runtime overrides)

### `~/.sdlc/config.yml` (User Global)

Created by `sdlc-tools setup`. Not committed to git — personal to each developer:

```yaml
sdlc:
  github_token: ghp_your_token_here
  prompt_file: /path/to/custom-prompt.txt
  # Any other fields (base_branch, etc.) can go here as personal defaults
```

### `.sdlc.yml` Reference

```yaml
sdlc:
  base_branch: develop           # Branch to diff against
  release_prefix: releases       # Release branch name prefix
  max_diff_length: 20000         # Max diff chars sent to AI
  comment_marker: "<!-- AI-SDLC-REPORT -->"  # Idempotent comment marker
```

### Environment Variables

| Variable | Maps to |
|---|---|
| `BASE_BRANCH` | `base_branch` |
| `RELEASE_PREFIX` | `release_prefix` |
| `RELEASE_TAG_NAME` | `release_tag_name` |
| `MAX_DIFF_LENGTH` | `max_diff_length` |
| `GITHUB_TOKEN` | `github_token` |
| `GITHUB_REPOSITORY` | `github_repository` |
| `GITHUB_EVENT_NAME` | `github_event_name` |
| `GITHUB_EVENT_PATH` | `github_event_path` |
| `AI_PROVIDER` | `ai_provider` |
| `AI_MODEL` | `ai_model` |
| `AI_API_KEY` | `ai_api_key` |
| `AI_BASE_URL` | `ai_base_url` |
| `AI_TIMEOUT` | `ai_timeout` |

---

---

## Custom Copilot Prompt

By default, sdlc-tools uses a built-in prompt template for AI code analysis. You can override it with your own:

1. Create a text file with your custom prompt (must end with the diff placeholder):

   ```text
   You are a security-focused code reviewer.
   Analyze this diff for vulnerabilities, auth issues, and data leaks.
   Here is the git diff:
   ```

2. Set it via setup:

   ```bash
   sdlc-tools setup --prompt-file ~/prompts/security-review.txt
   ```

   Or add it to `~/.sdlc/config.yml`:

   ```yaml
   sdlc:
     prompt_file: ~/prompts/security-review.txt
   ```

The tool will read the prompt file at runtime. If the file is missing, it falls back to the bundled default.

---

## Multi-Model AI Support

sdlc-tools supports **5 AI providers** out of the box. Choose the one that fits your workflow and budget:

| Provider | API Endpoint | Key Required | Default Model | Free? |
|---|---|---|---|---|
| `copilot` | `gh copilot` CLI (subprocess) | Copilot subscription | — | ✗ (subscription) |
| `openai` | `api.openai.com/v1/chat/completions` | `OPENAI_API_KEY` | `gpt-4o` | ✗ |
| `anthropic` | `api.anthropic.com/v1/messages` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-20250514` | ✗ |
| `gemini` | `generativelanguage.googleapis.com` | `GEMINI_API_KEY` | `gemini-2.0-flash` | ✓ (free tier) |
| `ollama` | `localhost:11434` (local) | **None** | `llama3.2` | ✓ (fully local) |

### Quick Setup

```bash
# Use OpenAI
sdlc-tools setup --provider openai --ai-key sk-your-key
sdlc-tools report

# Use Gemini (free tier)
sdlc-tools setup --provider gemini --ai-key AIza-your-key
sdlc-tools report

# Use Ollama (free, local — no API key needed)
# First: install Ollama and run `ollama serve`
sdlc-tools setup --provider ollama
sdlc-tools report

# Override at runtime
sdlc-tools report --provider anthropic --model claude-sonnet-4-20250514
```

### Config Example

In `~/.sdlc/config.yml`:

```yaml
sdlc:
  github_token: ghp_...
  ai_provider: openai        # copilot | openai | anthropic | gemini | ollama
  ai_model: gpt-4o           # optional model override
  ai_api_key: sk-...          # or set via env var (OPENAI_API_KEY, etc.)
  ai_base_url: ""             # custom endpoint for proxies or self-hosted
  ai_timeout: 120             # seconds
```

### API Key Resolution

Keys are resolved in this order:
1. `ai_api_key` in config (CLI arg → env var → config file)
2. Provider-specific env var (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`)
3. If neither is found → error (except Ollama, which needs no key)

---

## GitHub Actions Usage

### AI Report on PR (pre-push hook alternative)

```yaml
name: AI Code Report
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
          AI_PROVIDER: openai  # or: anthropic, gemini, ollama, copilot
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

### Release Tagging on PR Merge

```yaml
name: SDLC CI Automation
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

## Pre-Push Hook Setup

```bash
# Install the tool
pip install git+https://github.com/White-Yaksha/sdlc-tools.git

# Add to your .git/hooks/pre-push
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
┌─────────────────────────────────────────────────┐
│                  CLI (click)                    │
│     sdlc-tools report | tag | setup | init      │
├────────────┬────────────┬───────────────────────┤
│  report.py │  tagger.py │       config.py       │
│  (AI + PR) │  (tags)    │  5-layer config merge │
├────────────┴────────────┤                       │
│         ai.py           │       log.py          │
│  (5 AI providers)       │    (structured log)   │
│  copilot | openai       │                       │
│  anthropic | gemini     │  prompts/__init__.py  │
│  ollama (free local)    │  (prompt loader)      │
├─────────────────────────┤                       │
│       client.py         │  prompts/default.txt  │
│  (GitHub API + auth)    │  (bundled template)   │
├─────────────────────────┤                       │
│        git.py           │                       │
│   (git operations)      │                       │
├─────────────────────────┤                       │
│        html.py          │                       │
│      (MD → HTML)        │                       │
└─────────────────────────┴───────────────────────┘
```

---

## Development

```bash
# Clone
git clone https://github.com/White-Yaksha/sdlc-tools.git
cd sdlc-tools

# Install in editable mode with dev deps
pip install -e ".[dev]"

# Lint
ruff check src/ tests/

# Test
pytest --tb=short -q

# Coverage
coverage run -m pytest && coverage report
```

---

## License

MIT — see [LICENSE](LICENSE).
