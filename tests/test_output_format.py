"""Tests for formatter config, helpers, HTML rendering, and pipeline output."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from whispercrawl.config import (
    CleanupConfig,
    Config,
    DirSummarizationConfig,
    FormatterConfig,
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
            f"watch_dir: {tmp_path}\nextensions: [.mp3]\nformatter:\n  format: {fmt}\n",
            encoding="utf-8",
        )
        return p

    def test_txt_accepted(self, tmp_path):
        from whispercrawl.config import load_config
        cfg = load_config(self._write_config(tmp_path, "txt"))
        assert cfg.formatter.format == "txt"

    def test_html_accepted(self, tmp_path):
        from whispercrawl.config import load_config
        cfg = load_config(self._write_config(tmp_path, "html"))
        assert cfg.formatter.format == "html"

    def test_unknown_format_raises(self, tmp_path):
        from whispercrawl.config import load_config
        with pytest.raises(ValueError, match="formatter.format"):
            load_config(self._write_config(tmp_path, "pdf"))

    def test_default_is_txt_when_absent(self, tmp_path):
        from whispercrawl.config import load_config
        p = tmp_path / "config.yaml"
        p.write_text(f"watch_dir: {tmp_path}\nextensions: [.mp3]\n", encoding="utf-8")
        cfg = load_config(p)
        assert cfg.formatter.format == "txt"

    def test_enabled_defaults_to_true(self, tmp_path):
        from whispercrawl.config import load_config
        p = tmp_path / "config.yaml"
        p.write_text(f"watch_dir: {tmp_path}\nextensions: [.mp3]\n", encoding="utf-8")
        cfg = load_config(p)
        assert cfg.formatter.enabled is True

    def test_enabled_can_be_set_false(self, tmp_path):
        from whispercrawl.config import load_config
        p = tmp_path / "config.yaml"
        p.write_text(
            f"watch_dir: {tmp_path}\nextensions: [.mp3]\nformatter:\n  format: html\n  enabled: false\n",
            encoding="utf-8",
        )
        cfg = load_config(p)
        assert cfg.formatter.enabled is False
        assert cfg.formatter.format == "html"


# ── HTML pipeline output ──────────────────────────────────────────────────────

def _html_config(tmp_path: Path) -> Config:
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=True,
        formatter=FormatterConfig(format="html"),
        transcription=TranscriptionConfig(output_suffix="", error_suffix="_err"),
        postprocessing=OllamaStepConfig(llm_enabled=False, regex_enabled=False),
        file_summarization=OllamaStepConfig(llm_enabled=False),
        dir_summarization=DirSummarizationConfig(llm_enabled=False),
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


# ── formatter enabled=false ───────────────────────────────────────────────────

class TestFormatterDisabled:
    def test_enabled_false_leaves_txt_even_when_format_is_html(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")
        cfg = Config(
            watch_dir=tmp_path,
            extensions=[".mp3"],
            rescan=True,
            formatter=FormatterConfig(format="html", enabled=False),
            transcription=TranscriptionConfig(output_suffix="", error_suffix="_err"),
            postprocessing=OllamaStepConfig(llm_enabled=False, regex_enabled=False),
            file_summarization=OllamaStepConfig(llm_enabled=False),
            dir_summarization=DirSummarizationConfig(llm_enabled=False),
            schedule=ScheduleConfig(),
            cleanup=CleanupConfig(targets=[]),
            logging=LoggingConfig(),
        )
        with patch(
            "whispercrawl.pipeline.transcriber.httpx.post",
            return_value=_mock_ok("transcript text"),
        ):
            run_pipeline(cfg)

        assert (tmp_path / "rec.txt").exists()
        assert not (tmp_path / "rec.html").exists()


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
            formatter=FormatterConfig(format="html"),
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
            formatter=FormatterConfig(format="html"),
            cleanup=CleanupConfig(targets=[""], on="success"),
            logging=LoggingConfig(),
        )
        run_cleanup(cfg)

        assert txt_out.exists()


# ── TXT pipeline output ───────────────────────────────────────────────────────

def _txt_config(tmp_path: Path) -> Config:
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=True,
        formatter=FormatterConfig(format="txt"),
        transcription=TranscriptionConfig(output_suffix="", error_suffix="_err"),
        postprocessing=OllamaStepConfig(llm_enabled=False, regex_enabled=False),
        file_summarization=OllamaStepConfig(llm_enabled=False),
        dir_summarization=DirSummarizationConfig(llm_enabled=False),
        schedule=ScheduleConfig(),
        cleanup=CleanupConfig(targets=[]),
        logging=LoggingConfig(),
    )


class TestTxtPipelineOutput:
    def test_txt_format_writes_txt_extension(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch(
            "whispercrawl.pipeline.transcriber.httpx.post",
            return_value=_mock_ok("transcript text"),
        ):
            run_pipeline(_txt_config(tmp_path))

        assert (tmp_path / "rec.txt").exists()
        assert not (tmp_path / "rec.html").exists()

    def test_txt_file_contains_plain_text(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch(
            "whispercrawl.pipeline.transcriber.httpx.post",
            return_value=_mock_ok("transcript text"),
        ):
            run_pipeline(_txt_config(tmp_path))

        assert (tmp_path / "rec.txt").read_text(encoding="utf-8") == "transcript text"


class TestConsolidatedFileResult:
    """EPIC-047: one per-file result = summary section then transcript."""

    def _config(self, tmp_path: Path) -> Config:
        return Config(
            watch_dir=tmp_path,
            extensions=[".mp3"],
            rescan=True,
            formatter=FormatterConfig(format="txt"),
            transcription=TranscriptionConfig(output_suffix="", error_suffix="_err"),
            postprocessing=OllamaStepConfig(llm_enabled=True, regex_enabled=False),
            file_summarization=OllamaStepConfig(llm_enabled=True),
            dir_summarization=DirSummarizationConfig(llm_enabled=False),
            schedule=ScheduleConfig(),
            cleanup=CleanupConfig(targets=[]),
            logging=LoggingConfig(),
        )

    def test_result_has_summary_then_transcript_and_no_sidecars(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")
        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", return_value="[SPEAKER_00]: hello"),
            patch("whispercrawl.pipeline.postprocessor.PostProcessor.process", return_value="[SPEAKER_00]: hello fixed"),
            patch("whispercrawl.pipeline.summarizer.Summarizer.summarize_file", return_value="THE SUMMARY"),
        ):
            run_pipeline(self._config(tmp_path))

        content = (tmp_path / "rec.txt").read_text(encoding="utf-8")
        assert "# Резюме" in content
        assert "# Транскрипция" in content
        assert content.index("THE SUMMARY") < content.index("hello fixed")
        assert not (tmp_path / "rec_fix.txt").exists()
        assert not (tmp_path / "rec_sum.txt").exists()


# ── Dir concat uses in-memory texts, not files on disk ────────────────────────

class TestDirConcatUsesMemoryTexts:
    def test_concat_receives_in_memory_text_not_files(self, tmp_path):
        """concat_transcriptions works from passed dict and does not call ollama."""
        from whispercrawl.pipeline.summarizer import Summarizer

        summarizer = Summarizer(DirSummarizationConfig(llm_enabled=True, output_suffix="_sum"))
        ollama_called = []
        summarizer._call_ollama = lambda text, file="": ollama_called.append(text) or ""

        result = summarizer.concat_transcriptions({"rec.mp3": "plain transcript"})

        assert "rec.mp3" in result
        assert "plain transcript" in result
        assert ollama_called == []  # concat_transcriptions must not call ollama

    def test_concat_ignores_files_on_disk(self, tmp_path):
        """Files on disk are irrelevant; only passed texts are concatenated."""
        from whispercrawl.pipeline.summarizer import Summarizer

        (tmp_path / "rec_sum.txt").write_text("on disk text", encoding="utf-8")

        summarizer = Summarizer(DirSummarizationConfig(llm_enabled=True, output_suffix="_sum"))
        result = summarizer.concat_transcriptions({"rec.mp3": "in-memory text"})

        assert "in-memory text" in result
        assert "on disk text" not in result


# ── Dir summarization runs before formatter (EPIC-030) ────────────────────────

class TestDirSumAfterFormatter:
    """Formatter must run after dir summarization so _sum.txt files are still present."""

    def _config(self, tmp_path: Path, fmt: str) -> Config:
        return Config(
            watch_dir=tmp_path,
            extensions=[".mp3"],
            rescan=True,
            formatter=FormatterConfig(format=fmt),
            transcription=TranscriptionConfig(output_suffix="", error_suffix="_err"),
            postprocessing=OllamaStepConfig(llm_enabled=False, regex_enabled=False),
            file_summarization=OllamaStepConfig(
                llm_enabled=True,
                output_suffix="_sum",
                error_suffix="_err",
            ),
            dir_summarization=DirSummarizationConfig(
                llm_enabled=True,
                output_suffix="_sum",
                error_suffix="_err",
            ),
            schedule=ScheduleConfig(),
            cleanup=CleanupConfig(targets=[]),
            logging=LoggingConfig(),
        )

    def _run(self, tmp_path: Path, fmt: str) -> None:
        (tmp_path / "rec.mp3").write_bytes(b"\x00")
        with (
            patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_mock_ok("transcript")),
            patch("whispercrawl.pipeline.summarizer.httpx.post", return_value=_mock_ok("summary")),
        ):
            run_pipeline(self._config(tmp_path, fmt))

    def test_md_dir_result_written_as_md(self, tmp_path):
        self._run(tmp_path, "md")
        assert (tmp_path / f"{tmp_path.name}.md").exists()

    def test_md_no_orphan_txt(self, tmp_path):
        self._run(tmp_path, "md")
        assert not (tmp_path / "rec_sum.txt").exists()
        assert not (tmp_path / "rec.txt").exists()
        assert not (tmp_path / f"{tmp_path.name}.txt").exists()

    def test_html_dir_result_written_as_html(self, tmp_path):
        self._run(tmp_path, "html")
        assert (tmp_path / f"{tmp_path.name}.html").exists()

    def test_html_no_orphan_txt(self, tmp_path):
        self._run(tmp_path, "html")
        assert not (tmp_path / "rec_sum.txt").exists()
        assert not (tmp_path / f"{tmp_path.name}.txt").exists()

    def test_txt_dir_result_succeeds(self, tmp_path):
        self._run(tmp_path, "txt")
        assert (tmp_path / f"{tmp_path.name}.txt").exists()


# ── Filename headers in concat output (EPIC-034) ─────────────────────────────

class TestConcatFilenameHeaders:
    def _summarizer(self):
        from whispercrawl.pipeline.summarizer import Summarizer
        return Summarizer(DirSummarizationConfig(llm_enabled=False))

    def test_single_file_header_present(self):
        result = self._summarizer().concat_transcriptions({"rec.mp3": "hello"})
        assert result == "rec.mp3\n\nhello"

    def test_two_files_both_headers_present(self):
        result = self._summarizer().concat_transcriptions({
            "b.mp3": "text_b",
            "a.mp3": "text_a",
        })
        assert "a.mp3" in result
        assert "b.mp3" in result
        assert "text_a" in result
        assert "text_b" in result

    def test_two_files_sorted_order(self):
        result = self._summarizer().concat_transcriptions({
            "b.mp3": "text_b",
            "a.mp3": "text_a",
        })
        assert result.index("a.mp3") < result.index("b.mp3")

    def test_two_files_separator_between_blocks(self):
        result = self._summarizer().concat_transcriptions({
            "a.mp3": "text_a",
            "b.mp3": "text_b",
        })
        assert result == "a.mp3\n\ntext_a\n\n---\n\nb.mp3\n\ntext_b"

    def test_empty_dict_raises(self):
        from whispercrawl.pipeline.summarizer import SummarizationError
        with pytest.raises(SummarizationError):
            self._summarizer().concat_transcriptions({})


# ── Formatter converts concat file (EPIC-034) ────────────────────────────────

class TestConcatFormatterPass:
    def _config(self, tmp_path: Path, fmt: str) -> Config:
        return Config(
            watch_dir=tmp_path,
            extensions=[".mp3"],
            rescan=True,
            formatter=FormatterConfig(format=fmt),
            transcription=TranscriptionConfig(output_suffix="", error_suffix="_err"),
            postprocessing=OllamaStepConfig(llm_enabled=False, regex_enabled=False),
            file_summarization=OllamaStepConfig(llm_enabled=False),
            dir_summarization=DirSummarizationConfig(llm_enabled=False),
            schedule=ScheduleConfig(),
            cleanup=CleanupConfig(targets=[]),
            logging=LoggingConfig(),
        )

    def _run(self, tmp_path: Path, fmt: str) -> None:
        (tmp_path / "rec.mp3").write_bytes(b"\x00")
        with patch(
            "whispercrawl.pipeline.transcriber.httpx.post",
            return_value=_mock_ok("transcript"),
        ):
            run_pipeline(self._config(tmp_path, fmt))

    def test_md_dir_result_written_as_md(self, tmp_path):
        self._run(tmp_path, "md")
        assert (tmp_path / f"{tmp_path.name}.md").exists()

    def test_md_no_orphan_txt(self, tmp_path):
        self._run(tmp_path, "md")
        assert not (tmp_path / f"{tmp_path.name}.txt").exists()

    def test_html_dir_result_written_as_html(self, tmp_path):
        self._run(tmp_path, "html")
        assert (tmp_path / f"{tmp_path.name}.html").exists()

    def test_html_no_orphan_txt(self, tmp_path):
        self._run(tmp_path, "html")
        assert not (tmp_path / f"{tmp_path.name}.txt").exists()

    def test_txt_dir_result_remains_txt(self, tmp_path):
        self._run(tmp_path, "txt")
        assert (tmp_path / f"{tmp_path.name}.txt").exists()


# ── Cleanup removes concat in correct format (EPIC-034) ──────────────────────

class TestConcatCleanup:
    def _config(self, tmp_path: Path, fmt: str) -> Config:
        return Config(
            watch_dir=tmp_path,
            extensions=[".mp3"],
            formatter=FormatterConfig(format=fmt),
            dir_summarization=DirSummarizationConfig(concat_suffix="_concat"),
            cleanup=CleanupConfig(targets=["_concat"], on="success"),
            logging=LoggingConfig(),
        )

    def test_md_cleanup_removes_concat_md(self, tmp_path):
        audio = tmp_path / "rec.mp3"
        audio.touch()
        concat = tmp_path / f"{tmp_path.name}_concat.md"
        concat.write_text("x")
        run_cleanup(self._config(tmp_path, "md"))
        assert not concat.exists()

    def test_md_cleanup_leaves_concat_txt_alone(self, tmp_path):
        audio = tmp_path / "rec.mp3"
        audio.touch()
        concat_txt = tmp_path / f"{tmp_path.name}_concat.txt"
        concat_txt.write_text("x")
        run_cleanup(self._config(tmp_path, "md"))
        assert concat_txt.exists()

    def test_html_cleanup_removes_concat_html(self, tmp_path):
        audio = tmp_path / "rec.mp3"
        audio.touch()
        concat = tmp_path / f"{tmp_path.name}_concat.html"
        concat.write_text("x")
        run_cleanup(self._config(tmp_path, "html"))
        assert not concat.exists()

    def test_txt_cleanup_removes_concat_txt(self, tmp_path):
        audio = tmp_path / "rec.mp3"
        audio.touch()
        concat = tmp_path / f"{tmp_path.name}_concat.txt"
        concat.write_text("x")
        run_cleanup(self._config(tmp_path, "txt"))
        assert not concat.exists()


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_ok(text: str) -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.text = text
    r.content = text.encode()
    r.json.return_value = {"message": {"content": text}}
    return r
