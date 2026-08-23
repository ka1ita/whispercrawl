"""Tests for Summarizer — per-file and per-directory modes."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from whispercrawl.config import OllamaStepConfig
from whispercrawl.pipeline.summarizer import Summarizer, SummarizationError


def _cfg(**kwargs) -> OllamaStepConfig:
    defaults = dict(
        url="http://localhost:11434",
        model="gemma3:1b",
        prompt="Summarise the text.",
        output_suffix="_sum",
    )
    defaults.update(kwargs)
    return OllamaStepConfig(**defaults)


def _mock_response(content: str = "Summary text", status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.text = content
    resp.content = content.encode()
    resp.json.return_value = {"message": {"content": content}}
    return resp


class TestSummarizeFile:
    def test_returns_ollama_response_content(self):
        cfg = _cfg()
        with patch("whispercrawl.pipeline.summarizer.httpx.post", return_value=_mock_response("Great summary")) as mock_post:
            result = Summarizer(cfg).summarize_file("Some transcript")
        assert result == "Great summary"

    def test_sends_prompt_as_system_message(self):
        cfg = _cfg(prompt="My custom prompt.")
        with patch("whispercrawl.pipeline.summarizer.httpx.post", return_value=_mock_response()) as mock_post:
            Summarizer(cfg).summarize_file("text")
        messages = mock_post.call_args.kwargs["json"]["messages"]
        assert messages[0] == {"role": "system", "content": "My custom prompt."}

    def test_sends_text_as_user_message(self):
        cfg = _cfg()
        with patch("whispercrawl.pipeline.summarizer.httpx.post", return_value=_mock_response()) as mock_post:
            Summarizer(cfg).summarize_file("The transcript body")
        messages = mock_post.call_args.kwargs["json"]["messages"]
        assert messages[1] == {"role": "user", "content": "The transcript body"}

    def test_uses_configured_model(self):
        cfg = _cfg(model="llama3.2")
        with patch("whispercrawl.pipeline.summarizer.httpx.post", return_value=_mock_response()) as mock_post:
            Summarizer(cfg).summarize_file("text")
        assert mock_post.call_args.kwargs["json"]["model"] == "llama3.2"

    def test_uses_configured_timeout(self):
        cfg = _cfg(timeout=120)
        with patch("whispercrawl.pipeline.summarizer.httpx.post", return_value=_mock_response()) as mock_post:
            Summarizer(cfg).summarize_file("text")
        assert mock_post.call_args.kwargs["timeout"] == 120

    def test_non_200_raises_summarization_error(self):
        cfg = _cfg()
        with patch("whispercrawl.pipeline.summarizer.httpx.post", return_value=_mock_response(status=500)):
            with pytest.raises(SummarizationError, match="ollama returned 500"):
                Summarizer(cfg).summarize_file("text")

    def test_request_error_raises_summarization_error(self):
        import httpx
        cfg = _cfg()
        with patch("whispercrawl.pipeline.summarizer.httpx.post", side_effect=httpx.ReadTimeout("timed out")):
            with pytest.raises(SummarizationError, match="ollama request failed"):
                Summarizer(cfg).summarize_file("text")

    def test_stream_false_in_request(self):
        cfg = _cfg()
        with patch("whispercrawl.pipeline.summarizer.httpx.post", return_value=_mock_response()) as mock_post:
            Summarizer(cfg).summarize_file("text")
        assert mock_post.call_args.kwargs["json"]["stream"] is False


class TestConcatTranscriptions:
    def test_joins_texts_with_separator(self):
        cfg = _cfg()
        result = Summarizer(cfg).concat_transcriptions({"a.mp3": "Text A", "b.mp3": "Text B"})
        assert "Text A" in result
        assert "Text B" in result
        assert "---" in result

    def test_sorted_by_filename(self):
        cfg = _cfg()
        result = Summarizer(cfg).concat_transcriptions({"z.mp3": "Z", "a.mp3": "A"})
        assert result.index("A") < result.index("Z")

    def test_single_file_no_separator(self):
        cfg = _cfg()
        result = Summarizer(cfg).concat_transcriptions({"only.mp3": "Solo text"})
        assert "only.mp3" in result
        assert "Solo text" in result
        assert "---" not in result

    def test_empty_dict_raises_error(self):
        cfg = _cfg()
        with pytest.raises(SummarizationError, match="No transcription texts"):
            Summarizer(cfg).concat_transcriptions({})

    def test_does_not_call_ollama(self):
        cfg = _cfg()
        with patch("whispercrawl.pipeline.summarizer.httpx.post") as mock_post:
            Summarizer(cfg).concat_transcriptions({"a.mp3": "Text"})
        mock_post.assert_not_called()
