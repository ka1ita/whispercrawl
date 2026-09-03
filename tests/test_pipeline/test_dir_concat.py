"""Integration tests for the one consolidated per-directory result (EPIC-033 → EPIC-047).

A processed directory now yields a single file — ``{prefix}{dirname}.{ext}`` —
holding the directory summary (when enabled) followed by every transcript
concatenated with filename headers. The old ``_concat`` / ``_sum`` sidecars are
gone.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from asr_crawler.config import (
    Config,
    DirSummarizationConfig,
    FormatterConfig,
    LoggingConfig,
    OllamaStepConfig,
    ScheduleConfig,
    TranscriptionConfig,
)
from asr_crawler.main import run_pipeline


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
    fmt: str = "txt",
) -> Config:
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=True,
        formatter=FormatterConfig(format=fmt),
        transcription=TranscriptionConfig(output_suffix=""),
        postprocessing=OllamaStepConfig(llm_enabled=False, regex_enabled=False),
        file_summarization=OllamaStepConfig(llm_enabled=False),
        dir_summarization=DirSummarizationConfig(
            llm_enabled=llm_enabled,
            concat_source=concat_source,
            underscore_prefix=underscore_prefix,
        ),
        schedule=ScheduleConfig(),
        logging=LoggingConfig(),
    )


def _dir_result(tmp_path: Path, ext: str = "txt", *, prefix: str = "") -> Path:
    return tmp_path / f"{prefix}{tmp_path.name}.{ext}"


class TestDirResultWritten:
    def test_result_written_as_txt(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch("asr_crawler.pipeline.transcriber.httpx.post", return_value=_ok_response("hello")):
            run_pipeline(_config(tmp_path, llm_enabled=False))

        result = _dir_result(tmp_path)
        assert result.exists()
        content = result.read_text(encoding="utf-8")
        assert "rec.mp3" in content
        assert "hello" in content

    def test_result_contains_all_transcripts_with_separator(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        (tmp_path / "b.mp3").write_bytes(b"\x00")

        with patch("asr_crawler.pipeline.transcriber.httpx.post", return_value=_ok_response("text")):
            run_pipeline(_config(tmp_path, llm_enabled=False))

        content = _dir_result(tmp_path).read_text(encoding="utf-8")
        assert "text" in content
        assert "---" in content  # separator between files

    def test_result_converted_to_html_format(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch("asr_crawler.pipeline.transcriber.httpx.post", return_value=_ok_response("hello")):
            run_pipeline(_config(tmp_path, llm_enabled=False, fmt="html"))

        assert _dir_result(tmp_path, "html").exists()
        assert not _dir_result(tmp_path, "txt").exists()

    def test_result_converted_to_md_format(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch("asr_crawler.pipeline.transcriber.httpx.post", return_value=_ok_response("hello")):
            run_pipeline(_config(tmp_path, llm_enabled=False, fmt="md"))

        assert _dir_result(tmp_path, "md").exists()
        assert not _dir_result(tmp_path, "txt").exists()

    def test_no_legacy_concat_or_sum_sidecars(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with (
            patch("asr_crawler.pipeline.transcriber.httpx.post", return_value=_ok_response("text")),
            patch("asr_crawler.pipeline.summarizer.httpx.post", return_value=_ok_response("summary")),
        ):
            run_pipeline(_config(tmp_path, llm_enabled=True))

        assert not (tmp_path / f"{tmp_path.name}_concat.txt").exists()
        assert not (tmp_path / f"{tmp_path.name}_sum.txt").exists()
        assert not (tmp_path / "rec_sum.txt").exists()


class TestUnderscorePrefix:
    def test_prefix_false_uses_dirname_only(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch("asr_crawler.pipeline.transcriber.httpx.post", return_value=_ok_response("text")):
            run_pipeline(_config(tmp_path, llm_enabled=False, underscore_prefix=False))

        assert _dir_result(tmp_path).exists()
        assert not _dir_result(tmp_path, prefix="_").exists()

    def test_prefix_true_prepends_underscore(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch("asr_crawler.pipeline.transcriber.httpx.post", return_value=_ok_response("text")):
            run_pipeline(_config(tmp_path, llm_enabled=False, underscore_prefix=True))

        assert _dir_result(tmp_path, prefix="_").exists()
        assert not _dir_result(tmp_path).exists()

    def test_prefix_true_with_llm_summary(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with (
            patch("asr_crawler.pipeline.transcriber.httpx.post", return_value=_ok_response("text")),
            patch("asr_crawler.pipeline.summarizer.httpx.post", return_value=_ok_response("summary")),
        ):
            run_pipeline(_config(tmp_path, llm_enabled=True, underscore_prefix=True))

        result = _dir_result(tmp_path, prefix="_")
        assert result.exists()
        assert "summary" in result.read_text(encoding="utf-8")
        assert not _dir_result(tmp_path).exists()


class TestLlmEnabledFlag:
    def test_llm_disabled_result_is_concat_only(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch("asr_crawler.pipeline.transcriber.httpx.post", return_value=_ok_response("body text")):
            run_pipeline(_config(tmp_path, llm_enabled=False))

        content = _dir_result(tmp_path).read_text(encoding="utf-8")
        assert "body text" in content
        assert "Резюме" not in content  # no summary section

    def test_llm_enabled_result_has_summary_and_transcript_sections(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        # patch the pipeline methods directly — transcriber and summarizer share
        # the same httpx module, so patching httpx.post in both places collides
        with (
            patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe", return_value="body text"),
            patch("asr_crawler.pipeline.summarizer.Summarizer.summarize_file", return_value="the summary"),
        ):
            run_pipeline(_config(tmp_path, llm_enabled=True))

        content = _dir_result(tmp_path).read_text(encoding="utf-8")
        assert "# Резюме" in content
        assert "the summary" in content
        assert "# Транскрипция" in content
        assert "body text" in content
        assert content.index("the summary") < content.index("body text")

    def test_llm_receives_concatenated_transcriptions(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        (tmp_path / "b.mp3").write_bytes(b"\x00")

        received_texts = []

        def capture_summarize(text, file=""):
            received_texts.append(text)
            return "dir summary"

        with (
            patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe", return_value="raw transcript"),
            patch("asr_crawler.pipeline.summarizer.Summarizer.summarize_file", side_effect=capture_summarize),
        ):
            run_pipeline(_config(tmp_path, llm_enabled=True))

        assert len(received_texts) == 1
        combined = received_texts[0]
        assert "raw transcript" in combined
        assert "---" in combined  # separator between the two files


class TestConcatSource:
    def test_original_source_uses_transcript(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch("asr_crawler.pipeline.transcriber.httpx.post", return_value=_ok_response("original transcript")):
            run_pipeline(_config(tmp_path, llm_enabled=False, concat_source="original"))

        content = _dir_result(tmp_path).read_text(encoding="utf-8")
        assert "original transcript" in content

    def test_postprocessed_falls_back_to_transcript_when_no_postprocessor(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with patch("asr_crawler.pipeline.transcriber.httpx.post", return_value=_ok_response("raw")):
            run_pipeline(_config(tmp_path, llm_enabled=False, concat_source="postprocessed"))

        content = _dir_result(tmp_path).read_text(encoding="utf-8")
        assert "raw" in content


class TestSummaryFormatterIntegration:
    def test_dir_result_respects_formatter_format_md(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with (
            patch("asr_crawler.pipeline.transcriber.httpx.post", return_value=_ok_response("text")),
            patch("asr_crawler.pipeline.summarizer.httpx.post", return_value=_ok_response("summary")),
        ):
            run_pipeline(_config(tmp_path, llm_enabled=True, fmt="md"))

        assert _dir_result(tmp_path, "md").exists()
        assert not _dir_result(tmp_path, "txt").exists()

    def test_dir_result_respects_formatter_format_html(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        with (
            patch("asr_crawler.pipeline.transcriber.httpx.post", return_value=_ok_response("text")),
            patch("asr_crawler.pipeline.summarizer.httpx.post", return_value=_ok_response("summary")),
        ):
            run_pipeline(_config(tmp_path, llm_enabled=True, fmt="html"))

        html = _dir_result(tmp_path, "html")
        assert html.exists()
        assert not _dir_result(tmp_path, "txt").exists()
        assert "<h1>" in html.read_text(encoding="utf-8")
