"""Tests for output_format: helpers, HTML rendering, format validation, HTML pipeline output."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from whispercrawl.config import (
    CleanupConfig,
    Config,
    LoggingConfig,
    OllamaStepConfig,
    ScheduleConfig,
    TranscriptionConfig,
)
from whispercrawl.main import output_path, render_output, run_cleanup, run_pipeline


# ── output_path ───────────────────────────────────────────────────────────────

class TestOutputPath:
    def test_txt_format_no_suffix(self, tmp_path):
        base = tmp_path / "meeting.mp3"
        assert output_path(base, "", "txt").name == "meeting.txt"

    def test_txt_format_with_suffix(self, tmp_path):
        base = tmp_path / "meeting.mp3"
        assert output_path(base, "_fix", "txt").name == "meeting_fix.txt"

    def test_html_format_no_suffix(self, tmp_path):
        base = tmp_path / "meeting.mp3"
        assert output_path(base, "", "html").name == "meeting.html"

    def test_html_format_with_suffix(self, tmp_path):
        base = tmp_path / "meeting.mp3"
        assert output_path(base, "_sum", "html").name == "meeting_sum.html"


# ── render_output ─────────────────────────────────────────────────────────────

class TestRenderOutput:
    def test_txt_returns_text_unchanged(self):
        assert render_output("hello world", "txt") == "hello world"

    def test_txt_preserves_empty_string(self):
        assert render_output("", "txt") == ""

    def test_html_wraps_in_pre(self):
        result = render_output("hello world", "html")
        assert "<pre>hello world</pre>" in result

    def test_html_has_doctype(self):
        result = render_output("text", "html")
        assert result.startswith("<!DOCTYPE html>")

    def test_html_has_charset_meta(self):
        result = render_output("text", "html")
        assert 'charset="utf-8"' in result

    def test_html_escapes_less_than(self):
        result = render_output("a < b", "html")
        assert "&lt;" in result
        assert "a < b" not in result

    def test_html_escapes_greater_than(self):
        result = render_output("a > b", "html")
        assert "&gt;" in result

    def test_html_escapes_ampersand(self):
        result = render_output("a & b", "html")
        assert "&amp;" in result


# ── format validation in load_config ─────────────────────────────────────────

class TestFormatValidation:
    def _write_config(self, tmp_path: Path, fmt: str) -> Path:
        p = tmp_path / "config.yaml"
        p.write_text(
            f"watch_dir: {tmp_path}\nextensions: [.mp3]\noutput_format: {fmt}\n",
            encoding="utf-8",
        )
        return p

    def test_txt_accepted(self, tmp_path):
        from whispercrawl.config import load_config
        cfg = load_config(self._write_config(tmp_path, "txt"))
        assert cfg.output_format == "txt"

    def test_html_accepted(self, tmp_path):
        from whispercrawl.config import load_config
        cfg = load_config(self._write_config(tmp_path, "html"))
        assert cfg.output_format == "html"

    def test_unknown_format_raises(self, tmp_path):
        from whispercrawl.config import load_config
        with pytest.raises(ValueError, match="output_format"):
            load_config(self._write_config(tmp_path, "pdf"))

    def test_default_is_txt_when_absent(self, tmp_path):
        from whispercrawl.config import load_config
        p = tmp_path / "config.yaml"
        p.write_text(f"watch_dir: {tmp_path}\nextensions: [.mp3]\n", encoding="utf-8")
        cfg = load_config(p)
        assert cfg.output_format == "txt"


# ── HTML pipeline output ──────────────────────────────────────────────────────

def _html_config(tmp_path: Path) -> Config:
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=True,
        output_format="html",
        transcription=TranscriptionConfig(output_suffix="", error_suffix="_err"),
        postprocessing=OllamaStepConfig(llm_enabled=False, regex_enabled=False),
        file_summarization=OllamaStepConfig(llm_enabled=False),
        dir_summarization=OllamaStepConfig(llm_enabled=False),
        schedule=ScheduleConfig(),
        cleanup=CleanupConfig(targets=[]),
        logging=LoggingConfig(),
    )


class TestHtmlPipelineOutput:
    def test_html_format_writes_html_extension(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch(
            "whispercrawl.pipeline.transcriber.httpx.post",
            return_value=_mock_ok("transcript text"),
        ):
            run_pipeline(_html_config(tmp_path))

        assert (tmp_path / "rec.html").exists()
        assert not (tmp_path / "rec.txt").exists()

    def test_html_file_contains_pre_wrapped_text(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch(
            "whispercrawl.pipeline.transcriber.httpx.post",
            return_value=_mock_ok("transcript text"),
        ):
            run_pipeline(_html_config(tmp_path))

        content = (tmp_path / "rec.html").read_text(encoding="utf-8")
        assert "<pre>transcript text</pre>" in content
        assert "<!DOCTYPE html>" in content

    def test_html_format_escapes_special_chars(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch(
            "whispercrawl.pipeline.transcriber.httpx.post",
            return_value=_mock_ok("a < b & c > d"),
        ):
            run_pipeline(_html_config(tmp_path))

        content = (tmp_path / "rec.html").read_text(encoding="utf-8")
        assert "&lt;" in content
        assert "&amp;" in content
        assert "&gt;" in content


# ── HTML cleanup ──────────────────────────────────────────────────────────────

class TestHtmlCleanup:
    def test_cleanup_removes_html_output_files(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        html_out = tmp_path / "call.html"
        html_out.write_text("x")
        fix_html = tmp_path / "call_fix.html"
        fix_html.write_text("x")

        cfg = Config(
            watch_dir=tmp_path,
            extensions=[".mp3"],
            output_format="html",
            cleanup=CleanupConfig(targets=["", "_fix"], on="success"),
            logging=LoggingConfig(),
        )
        run_cleanup(cfg)

        assert not html_out.exists()
        assert not fix_html.exists()
        assert audio.exists()

    def test_html_cleanup_does_not_remove_txt_files(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        txt_out = tmp_path / "call.txt"
        txt_out.write_text("x")

        cfg = Config(
            watch_dir=tmp_path,
            extensions=[".mp3"],
            output_format="html",
            cleanup=CleanupConfig(targets=[""], on="success"),
            logging=LoggingConfig(),
        )
        run_cleanup(cfg)

        assert txt_out.exists()


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_ok(text: str) -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.text = text
    r.content = text.encode()
    r.json.return_value = {"message": {"content": text}}
    return r
