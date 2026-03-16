"""AI provider abstraction — pluggable backends for code analysis."""

from __future__ import annotations

import abc
import os
import re
import subprocess
import tempfile
from typing import TYPE_CHECKING

import requests

from sdlc_tools.log import get_logger

if TYPE_CHECKING:
    from sdlc_tools.config import SdlcConfig

log = get_logger("ai")

# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class AIProvider(abc.ABC):
    """Base class for AI analysis providers."""

    name: str = "base"

    @abc.abstractmethod
    def analyze(self, prompt: str, diff: str) -> str:
        """Send *prompt + diff* to the AI backend and return Markdown."""

    @property
    def display_name(self) -> str:
        """Human-readable provider + model label for report metadata."""
        model = getattr(self, "model", None)
        if model:
            return f"{self.name} ({model})"
        return self.name


# ---------------------------------------------------------------------------
# Copilot — gh copilot CLI (requires gh CLI installed)
# ---------------------------------------------------------------------------


class CopilotProvider(AIProvider):
    """Invokes ``gh copilot`` CLI via subprocess.

    NOTE: This is the **only** provider that requires the GitHub CLI (``gh``)
    to be installed. All other providers use direct HTTP calls with no
    external dependencies. If you don't have ``gh`` installed, use a
    different provider (e.g. gemini, ollama, openai, anthropic).
    """

    name = "copilot"
    _MAX_RETRIES = 2

    def __init__(self, model: str = "", timeout: int = 120) -> None:
        self.model = model
        self.timeout = timeout

    # gh.exe passes arguments through cmd.exe which has an 8191-char limit.
    _CMD_LINE_SAFE_LEN = 7000

    def analyze(self, prompt: str, diff: str) -> str:
        full_prompt = prompt + diff

        if len(full_prompt) <= self._CMD_LINE_SAFE_LEN:
            return self._run(["-p", full_prompt])

        # Prompt too long for a command-line argument — write to a temp file
        # and pass a short instruction that references it.
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False,
        )
        try:
            tmp.write(full_prompt)
            tmp.close()
            return self._run([
                "-p",
                f"Read the file at {tmp.name} and follow the instructions "
                "inside it. Return only the Markdown report, nothing else.",
            ])
        finally:
            os.unlink(tmp.name)

    def _run(self, prompt_args: list[str]) -> str:
        """Execute ``gh copilot`` with the given prompt arguments.

        Retries once on timeout to handle intermittent slowness.
        """
        cmd = [
            "gh", "copilot", "--",
            *prompt_args,
            "--allow-all-tools",
            "--autopilot",
            "-s",
        ]
        if self.model:
            cmd.extend(["--model", self.model])

        last_exc: RuntimeError | None = None
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    timeout=self.timeout,
                    encoding="utf-8",
                    errors="replace",
                )
            except FileNotFoundError as exc:
                raise RuntimeError(
                    "gh CLI not found. Install it (https://cli.github.com) to use the"
                    " Copilot provider, or switch to another provider"
                    " (e.g. --provider gemini).",
                ) from exc
            except subprocess.TimeoutExpired:
                last_exc = RuntimeError(
                    f"Copilot CLI timed out after {self.timeout}s"
                    f" (attempt {attempt}/{self._MAX_RETRIES}).",
                )
                log.warning(
                    "Copilot CLI timed out after %ds (attempt %d/%d). %s",
                    self.timeout,
                    attempt,
                    self._MAX_RETRIES,
                    "Retrying..." if attempt < self._MAX_RETRIES else "Giving up.",
                )
                continue

            if result.returncode != 0:
                raise RuntimeError(f"Copilot CLI failed: {result.stderr.strip()}")

            return self._clean_copilot_output((result.stdout or "").strip())

        raise last_exc  # type: ignore[misc]

    # Copilot CLI emits tool-use progress lines, shell commands, working-
    # directory markers, and internal narration before the actual report.
    # Rather than pattern-matching every variation, we strip everything
    # before the first Markdown heading — the report always starts with one.
    _HEADING_RE = re.compile(r"^#{1,6}\s")

    @classmethod
    def _clean_copilot_output(cls, text: str) -> str:
        lines = text.splitlines()
        # Find the first Markdown heading — everything before it is preamble.
        start = 0
        for idx, ln in enumerate(lines):
            if cls._HEADING_RE.match(ln):
                start = idx
                break
        return "\n".join(lines[start:]).strip()


# ---------------------------------------------------------------------------
# OpenAI — chat completions API
# ---------------------------------------------------------------------------


class OpenAIProvider(AIProvider):
    """Calls the OpenAI chat completions API."""

    name = "openai"
    _DEFAULT_MODEL = "gpt-4o"

    def __init__(
        self,
        api_key: str,
        model: str = "",
        base_url: str = "",
        timeout: int = 120,
    ) -> None:
        self.api_key = api_key
        self.model = model or self._DEFAULT_MODEL
        self.base_url = (base_url or "https://api.openai.com").rstrip("/")
        self.timeout = timeout

    def analyze(self, prompt: str, diff: str) -> str:
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt.rstrip()},
                {"role": "user", "content": diff},
            ],
            "temperature": 0.2,
        }
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"OpenAI API error {resp.status_code}: {resp.text[:300]}",
            )
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


# ---------------------------------------------------------------------------
# Anthropic — messages API
# ---------------------------------------------------------------------------


class AnthropicProvider(AIProvider):
    """Calls the Anthropic messages API."""

    name = "anthropic"
    _DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def __init__(
        self,
        api_key: str,
        model: str = "",
        base_url: str = "",
        timeout: int = 120,
    ) -> None:
        self.api_key = api_key
        self.model = model or self._DEFAULT_MODEL
        self.base_url = (base_url or "https://api.anthropic.com").rstrip("/")
        self.timeout = timeout

    def analyze(self, prompt: str, diff: str) -> str:
        url = f"{self.base_url}/v1/messages"
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "system": prompt.rstrip(),
            "messages": [{"role": "user", "content": diff}],
        }
        resp = requests.post(
            url,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Anthropic API error {resp.status_code}: {resp.text[:300]}",
            )
        data = resp.json()
        return data["content"][0]["text"].strip()


# ---------------------------------------------------------------------------
# Gemini — Google Generative Language API
# ---------------------------------------------------------------------------


class GeminiProvider(AIProvider):
    """Calls the Google Gemini (Generative Language) API."""

    name = "gemini"
    _DEFAULT_MODEL = "gemini-2.0-flash"

    def __init__(
        self,
        api_key: str,
        model: str = "",
        base_url: str = "",
        timeout: int = 120,
    ) -> None:
        self.api_key = api_key
        self.model = model or self._DEFAULT_MODEL
        self.base_url = (
            base_url or "https://generativelanguage.googleapis.com"
        ).rstrip("/")
        self.timeout = timeout

    def analyze(self, prompt: str, diff: str) -> str:
        url = (
            f"{self.base_url}/v1beta/models/{self.model}:generateContent"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt.rstrip() + "\n\n" + diff}]}],
            "generationConfig": {"temperature": 0.2},
        }
        resp = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            json=payload,
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Gemini API error {resp.status_code}: {resp.text[:300]}",
            )
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()


# ---------------------------------------------------------------------------
# Ollama — local open-source models (free, no API key)
# ---------------------------------------------------------------------------


class OllamaProvider(AIProvider):
    """Calls a locally running Ollama server (free, no API key)."""

    name = "ollama"
    _DEFAULT_MODEL = "llama3.2"

    def __init__(
        self,
        model: str = "",
        base_url: str = "",
        timeout: int = 120,
    ) -> None:
        self.model = model or self._DEFAULT_MODEL
        self.base_url = (base_url or "http://localhost:11434").rstrip("/")
        self.timeout = timeout

    def analyze(self, prompt: str, diff: str) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt.rstrip() + "\n\n" + diff,
            "stream": False,
        }
        try:
            resp = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
            )
        except requests.ConnectionError as exc:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Ensure Ollama is running (ollama serve).",
            ) from exc
        if resp.status_code != 200:
            raise RuntimeError(
                f"Ollama error {resp.status_code}: {resp.text[:300]}",
            )
        data = resp.json()
        return data.get("response", "").strip()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_ENV_KEY_MAP: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

_PROVIDERS: dict[str, type[AIProvider]] = {
    "copilot": CopilotProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
}


def _resolve_api_key(config: SdlcConfig, provider_name: str) -> str:
    """Resolve API key from config → env var."""
    if config.ai_api_key:
        return config.ai_api_key
    env_var = _ENV_KEY_MAP.get(provider_name, "")
    if env_var:
        key = os.environ.get(env_var, "")
        if key:
            return key
    return ""


def get_provider(config: SdlcConfig) -> AIProvider:
    """Instantiate the configured AI provider.

    Raises ``ValueError`` if the provider is unknown or a required key
    is missing.
    """
    name = config.ai_provider.lower()
    if name not in _PROVIDERS:
        raise ValueError(
            f"Unknown AI provider '{name}'. "
            f"Choose from: {', '.join(_PROVIDERS)}",
        )

    timeout = config.ai_timeout
    model = config.ai_model
    base_url = config.ai_base_url

    if name == "copilot":
        return CopilotProvider(model=model, timeout=timeout)

    if name == "ollama":
        return OllamaProvider(model=model, base_url=base_url, timeout=timeout)

    # Providers that require an API key.
    api_key = _resolve_api_key(config, name)
    if not api_key:
        env_var = _ENV_KEY_MAP.get(name, "AI_API_KEY")
        raise ValueError(
            f"No API key for '{name}'. "
            f"Set ai_api_key in config or export {env_var}.",
        )

    cls = _PROVIDERS[name]
    return cls(api_key=api_key, model=model, base_url=base_url, timeout=timeout)  # type: ignore[call-arg]
