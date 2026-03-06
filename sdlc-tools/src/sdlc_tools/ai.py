"""AI provider abstraction — pluggable backends for code analysis."""

from __future__ import annotations

import abc
import os
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


# ---------------------------------------------------------------------------
# Copilot — gh copilot CLI (existing behaviour)
# ---------------------------------------------------------------------------


class CopilotProvider(AIProvider):
    """Invokes ``gh copilot`` CLI via subprocess."""

    name = "copilot"

    def __init__(self, timeout: int = 120) -> None:
        self.timeout = timeout

    def analyze(self, prompt: str, diff: str) -> str:
        full_prompt = prompt + diff
        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8",
            ) as tmp:
                tmp.write(full_prompt)
                tmp_path = tmp.name

            short_prompt = (
                f"Read the file at {tmp_path} and follow the instructions inside it. "
                "Return only the Markdown report, nothing else."
            )
            result = subprocess.run(
                ["gh", "copilot", "--", "-p", short_prompt, "--allow-all-tools"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as exc:
            raise RuntimeError("gh CLI not found. Install it and try again.") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Copilot CLI timed out after {self.timeout}s.",
            ) from exc
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

        if result.returncode != 0:
            raise RuntimeError(f"Copilot CLI failed: {result.stderr.strip()}")

        return (result.stdout or "").strip()


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
            f"?key={self.api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt.rstrip() + "\n\n" + diff}]}],
            "generationConfig": {"temperature": 0.2},
        }
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json"},
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
        return CopilotProvider(timeout=timeout)

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
