"""Tests for post-processor regex and ollama integration."""
from unittest.mock import MagicMock, patch

import pytest

from whispercrawl.config import OllamaStepConfig
from whispercrawl.pipeline.postprocessor import PostProcessor


@pytest.fixture
def config():
    return OllamaStepConfig(
        url="http://localhost:11434",
        model="llama3.2",
        prompt="Fix transcription errors.",
        output_suffix="_fix.txt",
    )


class TestRegexCleanup:
    def test_removes_pattern(self, config):
        proc = PostProcessor(config, regex_patterns=[r"\[inaudible\]"])
        # Patch ollama to return input unchanged
        with patch.object(proc, "_call_ollama", side_effect=lambda t: t):
            result = proc.process("Hello [inaudible] world")
        assert "[inaudible]" not in result

    def test_no_patterns_passes_through(self, config):
        proc = PostProcessor(config)
        with patch.object(proc, "_call_ollama", side_effect=lambda t: t):
            result = proc.process("Hello world")
        assert result == "Hello world"


class TestOllamaIntegration:
    def test_calls_ollama_with_prompt(self, config):
        proc = PostProcessor(config)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": "Fixed text"}}

        with patch("whispercrawl.pipeline.postprocessor.httpx.post", return_value=mock_response) as mock_post:
            result = proc.process("Raw text")

        assert result == "Fixed text"
        call_json = mock_post.call_args.kwargs["json"]
        assert call_json["messages"][0]["content"] == config.prompt


class TestEnabledFlags:
    def test_both_enabled_applies_regex_then_llm(self):
        cfg = OllamaStepConfig(llm_enabled=True, regex_enabled=True)
        proc = PostProcessor(cfg, regex_patterns=[r"\[noise\]"])
        with patch.object(proc, "_call_ollama", return_value="LLM result") as mock_llm:
            result = proc.process("hello [noise] world")
        mock_llm.assert_called_once_with("hello  world")
        assert result == "LLM result"

    def test_regex_disabled_skips_regex_calls_llm(self):
        cfg = OllamaStepConfig(llm_enabled=True, regex_enabled=False)
        proc = PostProcessor(cfg, regex_patterns=[r"\[noise\]"])
        with patch.object(proc, "_call_ollama", return_value="LLM result") as mock_llm:
            result = proc.process("hello [noise] world")
        mock_llm.assert_called_once_with("hello [noise] world")
        assert result == "LLM result"

    def test_llm_disabled_applies_regex_no_ollama_call(self):
        cfg = OllamaStepConfig(llm_enabled=False, regex_enabled=True)
        proc = PostProcessor(cfg, regex_patterns=[r"\[noise\]"])
        with patch.object(proc, "_call_ollama") as mock_llm:
            result = proc.process("hello [noise] world")
        mock_llm.assert_not_called()
        assert result == "hello  world"

    def test_both_disabled_returns_input_unchanged(self):
        cfg = OllamaStepConfig(llm_enabled=False, regex_enabled=False)
        proc = PostProcessor(cfg, regex_patterns=[r"\[noise\]"])
        with patch.object(proc, "_call_ollama") as mock_llm:
            result = proc.process("hello [noise] world")
        mock_llm.assert_not_called()
        assert result == "hello [noise] world"
