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


class TestSummarizeDirectory:
    def test_combines_summary_files_and_calls_ollama(self, tmp_path):
        (tmp_path / "a_sum.txt").write_text("Summary A", encoding="utf-8")
        (tmp_path / "b_sum.txt").write_text("Summary B", encoding="utf-8")

        cfg = _cfg()
        with patch("whispercrawl.pipeline.summarizer.httpx.post", return_value=_mock_response("Combined")) as mock_post:
            result = Summarizer(cfg).summarize_directory(tmp_path, "_sum")

        assert result == "Combined"
        user_content = mock_post.call_args.kwargs["json"]["messages"][1]["content"]
        assert "Summary A" in user_content
        assert "Summary B" in user_content
        assert "---" in user_content

    def test_summaries_joined_in_sorted_order(self, tmp_path):
        (tmp_path / "z_sum.txt").write_text("Z", encoding="utf-8")
        (tmp_path / "a_sum.txt").write_text("A", encoding="utf-8")

        cfg = _cfg()
        with patch("whispercrawl.pipeline.summarizer.httpx.post", return_value=_mock_response()) as mock_post:
            Summarizer(cfg).summarize_directory(tmp_path, "_sum")

        content = mock_post.call_args.kwargs["json"]["messages"][1]["content"]
        assert content.index("A") < content.index("Z")

    def test_no_summary_files_raises_error(self, tmp_path):
        cfg = _cfg()
        with pytest.raises(SummarizationError, match="No summary files found"):
            Summarizer(cfg).summarize_directory(tmp_path, "_sum")

    def test_ignores_files_with_wrong_suffix(self, tmp_path):
        (tmp_path / "a.txt").write_text("raw transcript", encoding="utf-8")

        cfg = _cfg()
        with pytest.raises(SummarizationError, match="No summary files found"):
            Summarizer(cfg).summarize_directory(tmp_path, "_sum")
