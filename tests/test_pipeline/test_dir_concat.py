"""Integration tests for EPIC-033: per-directory transcription concatenation."""
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
from whispercrawl.main import run_pipeline


def _ok_response(text: str = "ok") -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.text = text
    r.content = text.encode()
    r.json.return_value = {"message": {"content": text}}
    return r


def _config(
    tmp_path: Path,
    *,
    llm_enabled: bool = True,
    concat_source: str = "postprocessed",
    underscore_prefix: bool = False,
    concat_suffix: str = "_concat",
    fmt: str = "txt",
) -> Config:
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=True,
        formatter=FormatterConfig(format=fmt),
        transcription=TranscriptionConfig(output_suffix="", error_suffix="_err"),
        postprocessing=OllamaStepConfig(llm_enabled=False, regex_enabled=False),
        file_summarization=OllamaStepConfig(llm_enabled=False),
        dir_summarization=DirSummarizationConfig(
            llm_enabled=llm_enabled,
            concat_source=concat_source,
            underscore_prefix=underscore_prefix,
            concat_suffix=concat_suffix,
            output_suffix="_sum",
            error_suffix="_err",
        ),
        schedule=ScheduleConfig(),
        cleanup=CleanupConfig(targets=[]),
        logging=LoggingConfig(),
    )


class TestConcatFileWritten:
    def test_concat_file_written_as_plain_txt(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response("hello")):
            run_pipeline(_config(tmp_path, llm_enabled=False))

        concat = tmp_path / f"{tmp_path.name}_concat.txt"
        assert concat.exists()
        assert concat.read_text(encoding="utf-8") == "hello"

    def test_concat_file_contains_transcript_text(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        (tmp_path / "b.mp3").write_bytes(b"\x00")

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response("text")):
            run_pipeline(_config(tmp_path, llm_enabled=False))

        concat = tmp_path / f"{tmp_path.name}_concat.txt"
        content = concat.read_text(encoding="utf-8")
        assert "text" in content
        assert "---" in content  # separator between files

    def test_concat_always_txt_even_in_html_format(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response("hello")):
            run_pipeline(_config(tmp_path, llm_enabled=False, fmt="html"))

        concat = tmp_path / f"{tmp_path.name}_concat.txt"
        assert concat.exists()
        assert not (tmp_path / f"{tmp_path.name}_concat.html").exists()

    def test_concat_always_txt_even_in_md_format(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response("hello")):
            run_pipeline(_config(tmp_path, llm_enabled=False, fmt="md"))

        concat = tmp_path / f"{tmp_path.name}_concat.txt"
        assert concat.exists()
        assert not (tmp_path / f"{tmp_path.name}_concat.md").exists()

    def test_custom_concat_suffix(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response("hello")):
            run_pipeline(_config(tmp_path, llm_enabled=False, concat_suffix="_all"))

        assert (tmp_path / f"{tmp_path.name}_all.txt").exists()
        assert not (tmp_path / f"{tmp_path.name}_concat.txt").exists()


class TestUnderscorePrefix:
    def test_prefix_false_uses_dirname_only(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response("text")):
            run_pipeline(_config(tmp_path, llm_enabled=False, underscore_prefix=False))

        assert (tmp_path / f"{tmp_path.name}_concat.txt").exists()
        assert not (tmp_path / f"_{tmp_path.name}_concat.txt").exists()

    def test_prefix_true_prepends_underscore(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response("text")):
            run_pipeline(_config(tmp_path, llm_enabled=False, underscore_prefix=True))

        assert (tmp_path / f"_{tmp_path.name}_concat.txt").exists()
        assert not (tmp_path / f"{tmp_path.name}_concat.txt").exists()

    def test_prefix_true_applies_to_llm_summary_too(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with (
            patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response("text")),
            patch("whispercrawl.pipeline.summarizer.httpx.post", return_value=_ok_response("summary")),
        ):
            run_pipeline(_config(tmp_path, llm_enabled=True, underscore_prefix=True))

        assert (tmp_path / f"_{tmp_path.name}_concat.txt").exists()
        assert (tmp_path / f"_{tmp_path.name}_sum.txt").exists()
        assert not (tmp_path / f"{tmp_path.name}_sum.txt").exists()

    def test_prefix_false_llm_summary_uses_dirname_only(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with (
            patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response("text")),
            patch("whispercrawl.pipeline.summarizer.httpx.post", return_value=_ok_response("summary")),
        ):
            run_pipeline(_config(tmp_path, llm_enabled=True, underscore_prefix=False))

        assert (tmp_path / f"{tmp_path.name}_sum.txt").exists()
        assert not (tmp_path / f"_{tmp_path.name}_sum.txt").exists()


class TestLlmEnabledFlag:
    def test_llm_enabled_false_skips_summary_file(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response("text")):
            run_pipeline(_config(tmp_path, llm_enabled=False))

        assert not (tmp_path / f"{tmp_path.name}_sum.txt").exists()

    def test_llm_enabled_false_still_writes_concat(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response("text")):
            run_pipeline(_config(tmp_path, llm_enabled=False))

        assert (tmp_path / f"{tmp_path.name}_concat.txt").exists()

    def test_llm_enabled_true_writes_both(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with (
            patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response("text")),
            patch("whispercrawl.pipeline.summarizer.httpx.post", return_value=_ok_response("summary")),
        ):
            run_pipeline(_config(tmp_path, llm_enabled=True))

        assert (tmp_path / f"{tmp_path.name}_concat.txt").exists()
        assert (tmp_path / f"{tmp_path.name}_sum.txt").exists()

    def test_llm_receives_concatenated_transcriptions(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        (tmp_path / "b.mp3").write_bytes(b"\x00")

        received_texts = []

        def capture_summarize(text, file=""):
            received_texts.append(text)
            return "dir summary"

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", return_value="raw transcript"),
            patch("whispercrawl.pipeline.summarizer.Summarizer.summarize_file", side_effect=capture_summarize),
        ):
            run_pipeline(_config(tmp_path, llm_enabled=True))

        # summarize_file is called once for the dir summary with the concatenated transcriptions
        assert len(received_texts) == 1
        combined = received_texts[0]
        assert "raw transcript" in combined
        assert "---" in combined  # separator between the two files


class TestConcatSource:
    def test_original_source_uses_transcript(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response("original transcript")):
            run_pipeline(_config(tmp_path, llm_enabled=False, concat_source="original"))

        content = (tmp_path / f"{tmp_path.name}_concat.txt").read_text(encoding="utf-8")
        assert "original transcript" in content

    def test_postprocessed_falls_back_to_transcript_when_no_postprocessor(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        # postprocessing is disabled, so no fixed_text; should fall back to transcript
        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response("raw")):
            run_pipeline(_config(tmp_path, llm_enabled=False, concat_source="postprocessed"))

        content = (tmp_path / f"{tmp_path.name}_concat.txt").read_text(encoding="utf-8")
        assert "raw" in content


class TestSummaryFormatterIntegration:
    def test_summary_respects_formatter_format_md(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with (
            patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response("text")),
            patch("whispercrawl.pipeline.summarizer.httpx.post", return_value=_ok_response("summary")),
        ):
            run_pipeline(_config(tmp_path, llm_enabled=True, fmt="md"))

        assert (tmp_path / f"{tmp_path.name}_sum.md").exists()
        assert not (tmp_path / f"{tmp_path.name}_sum.txt").exists()
        # concat file always .txt
        assert (tmp_path / f"{tmp_path.name}_concat.txt").exists()

    def test_summary_respects_formatter_format_html(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with (
            patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response("text")),
            patch("whispercrawl.pipeline.summarizer.httpx.post", return_value=_ok_response("summary")),
        ):
            run_pipeline(_config(tmp_path, llm_enabled=True, fmt="html"))

        assert (tmp_path / f"{tmp_path.name}_sum.html").exists()
        assert not (tmp_path / f"{tmp_path.name}_sum.txt").exists()
        assert (tmp_path / f"{tmp_path.name}_concat.txt").exists()
