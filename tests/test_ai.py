"""Tests for the AI provider abstraction."""

from __future__ import annotations

import pytest
import responses

from sdlc_tools.ai import (
    AnthropicProvider,
    CopilotProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAIProvider,
    get_provider,
)
from sdlc_tools.config import SdlcConfig

# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


class TestOpenAIProvider:

    @responses.activate
    def test_analyze_success(self) -> None:
        responses.add(
            responses.POST,
            "https://api.openai.com/v1/chat/completions",
            json={
                "choices": [{"message": {"content": "## Summary\nAll good."}}],
            },
            status=200,
        )
        provider = OpenAIProvider(api_key="sk-test", model="gpt-4o")
        result = provider.analyze("Analyze this:", "diff content")
        assert "Summary" in result
        assert result == "## Summary\nAll good."

    @responses.activate
    def test_analyze_error_raises(self) -> None:
        responses.add(
            responses.POST,
            "https://api.openai.com/v1/chat/completions",
            json={"error": {"message": "rate limit"}},
            status=429,
        )
        provider = OpenAIProvider(api_key="sk-test")
        with pytest.raises(RuntimeError, match="OpenAI API error 429"):
            provider.analyze("prompt", "diff")

    @responses.activate
    def test_custom_base_url(self) -> None:
        responses.add(
            responses.POST,
            "https://my-proxy.example.com/v1/chat/completions",
            json={"choices": [{"message": {"content": "ok"}}]},
            status=200,
        )
        provider = OpenAIProvider(
            api_key="sk-test",
            base_url="https://my-proxy.example.com",
        )
        result = provider.analyze("p", "d")
        assert result == "ok"


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


class TestAnthropicProvider:

    @responses.activate
    def test_analyze_success(self) -> None:
        responses.add(
            responses.POST,
            "https://api.anthropic.com/v1/messages",
            json={"content": [{"text": "## Report\nLooks fine."}]},
            status=200,
        )
        provider = AnthropicProvider(api_key="sk-ant-test")
        result = provider.analyze("Analyze:", "diff")
        assert "Report" in result

    @responses.activate
    def test_analyze_error_raises(self) -> None:
        responses.add(
            responses.POST,
            "https://api.anthropic.com/v1/messages",
            json={"error": {"message": "invalid key"}},
            status=401,
        )
        provider = AnthropicProvider(api_key="bad-key")
        with pytest.raises(RuntimeError, match="Anthropic API error 401"):
            provider.analyze("p", "d")


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------


class TestGeminiProvider:

    @responses.activate
    def test_analyze_success(self) -> None:
        responses.add(
            responses.POST,
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash"
            ":generateContent",
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "## Gemini Report\nOK."}]}},
                ],
            },
            status=200,
        )
        provider = GeminiProvider(api_key="AIza-test")
        result = provider.analyze("Analyze:", "diff")
        assert "Gemini Report" in result

    @responses.activate
    def test_analyze_error_raises(self) -> None:
        responses.add(
            responses.POST,
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash"
            ":generateContent",
            json={"error": {"message": "bad key"}},
            status=403,
        )
        provider = GeminiProvider(api_key="bad")
        with pytest.raises(RuntimeError, match="Gemini API error 403"):
            provider.analyze("p", "d")


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------


class TestOllamaProvider:

    @responses.activate
    def test_analyze_success(self) -> None:
        responses.add(
            responses.POST,
            "http://localhost:11434/api/generate",
            json={"response": "## Local Report\nDone."},
            status=200,
        )
        provider = OllamaProvider(model="llama3.2")
        result = provider.analyze("Analyze:", "diff")
        assert "Local Report" in result

    @responses.activate
    def test_analyze_error_raises(self) -> None:
        responses.add(
            responses.POST,
            "http://localhost:11434/api/generate",
            json={"error": "model not found"},
            status=404,
        )
        provider = OllamaProvider()
        with pytest.raises(RuntimeError, match="Ollama error 404"):
            provider.analyze("p", "d")

    def test_connection_error(self) -> None:
        from unittest.mock import patch

        import requests as _req

        provider = OllamaProvider()
        with (
            patch("sdlc_tools.ai.requests.post", side_effect=_req.ConnectionError("refused")),
            pytest.raises(RuntimeError, match="Cannot connect to Ollama"),
        ):
            provider.analyze("p", "d")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestGetProvider:

    def test_copilot_default(self) -> None:
        cfg = SdlcConfig(ai_provider="copilot")
        provider = get_provider(cfg)
        assert provider.name == "copilot"

    def test_copilot_cleans_status_lines(self) -> None:
        raw = (
            "● Read ~\\AppData\\Local\\Temp\\tmpfths2af3.txt\n"
            "└ 818 lines read\n"
            "# Impact Report\n"
            "Some content here.\n"
        )
        cleaned = CopilotProvider._clean_copilot_output(raw)
        assert "● Read" not in cleaned
        assert "└ 818" not in cleaned
        assert "# Impact Report" in cleaned
        assert "Some content here." in cleaned

    def test_openai_with_key(self) -> None:
        cfg = SdlcConfig(ai_provider="openai", ai_api_key="sk-test")
        provider = get_provider(cfg)
        assert provider.name == "openai"

    def test_anthropic_with_key(self) -> None:
        cfg = SdlcConfig(ai_provider="anthropic", ai_api_key="sk-ant")
        provider = get_provider(cfg)
        assert provider.name == "anthropic"

    def test_gemini_with_key(self) -> None:
        cfg = SdlcConfig(ai_provider="gemini", ai_api_key="AIza")
        provider = get_provider(cfg)
        assert provider.name == "gemini"

    def test_ollama_no_key_needed(self) -> None:
        cfg = SdlcConfig(ai_provider="ollama")
        provider = get_provider(cfg)
        assert provider.name == "ollama"

    def test_unknown_provider_raises(self) -> None:
        cfg = SdlcConfig(ai_provider="foobar")
        with pytest.raises(ValueError, match="Unknown AI provider"):
            get_provider(cfg)

    def test_missing_key_raises(self) -> None:
        cfg = SdlcConfig(ai_provider="openai", ai_api_key="")
        with pytest.raises(ValueError, match="No API key"):
            get_provider(cfg)

    def test_env_var_key_resolution(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
        cfg = SdlcConfig(ai_provider="openai")
        provider = get_provider(cfg)
        assert provider.name == "openai"

    def test_model_override(self) -> None:
        cfg = SdlcConfig(
            ai_provider="openai", ai_api_key="sk-test", ai_model="gpt-3.5-turbo",
        )
        provider = get_provider(cfg)
        assert isinstance(provider, OpenAIProvider)
        assert provider.model == "gpt-3.5-turbo"

    def test_base_url_override(self) -> None:
        cfg = SdlcConfig(
            ai_provider="openai",
            ai_api_key="sk-test",
            ai_base_url="https://proxy.example.com",
        )
        provider = get_provider(cfg)
        assert isinstance(provider, OpenAIProvider)
        assert "proxy.example.com" in provider.base_url
