"""Tests for _err.txt cleanup after successful pipeline execution."""
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
from whispercrawl.main import run_pipeline


def _ok_response(text: str = "transcribed") -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.text = text
    r.content = text.encode()
    r.json.return_value = {"message": {"content": text}}
    return r


def _err_response() -> MagicMock:
    r = MagicMock()
    r.status_code = 500
    r.text = "internal error"
    r.content = b"internal error"
    return r


def _config(tmp_path: Path, *, postprocessing=False, file_summarization=False, dir_summarization=False) -> Config:
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=True,
        transcription=TranscriptionConfig(output_suffix="", error_suffix="_err"),
        postprocessing=OllamaStepConfig(llm_enabled=postprocessing, regex_enabled=False),
        file_summarization=OllamaStepConfig(llm_enabled=file_summarization, output_suffix="_sum"),
        dir_summarization=OllamaStepConfig(llm_enabled=dir_summarization, output_suffix="_sum"),
        schedule=ScheduleConfig(),
        cleanup=CleanupConfig(targets=[]),
        logging=LoggingConfig(),
    )


class TestPerFileErrCleanup:
    def test_err_removed_after_full_success(self, tmp_path):
        audio = tmp_path / "meeting.mp3"
        audio.touch()
        err = tmp_path / "meeting_err.txt"
        err.write_text("previous error", encoding="utf-8")

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response()):
            run_pipeline(_config(tmp_path))

        assert not err.exists()
        assert (tmp_path / "meeting.txt").exists()

    def test_no_err_file_is_no_op(self, tmp_path):
        audio = tmp_path / "meeting.mp3"
        audio.touch()

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response()):
            run_pipeline(_config(tmp_path))

        assert not (tmp_path / "meeting_err.txt").exists()

    def test_err_preserved_when_postprocessing_fails(self, tmp_path):
        audio = tmp_path / "meeting.mp3"
        audio.touch()
        err = tmp_path / "meeting_err.txt"
        err.write_text("previous error", encoding="utf-8")

        with (
            patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response()),
            patch("whispercrawl.pipeline.postprocessor.httpx.post", return_value=_err_response()),
        ):
            run_pipeline(_config(tmp_path, postprocessing=True))

        assert err.exists()

    def test_err_preserved_when_file_summarization_fails(self, tmp_path):
        audio = tmp_path / "meeting.mp3"
        audio.touch()
        err = tmp_path / "meeting_err.txt"
        err.write_text("previous error", encoding="utf-8")

        with (
            patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response()),
            patch("whispercrawl.pipeline.summarizer.httpx.post", return_value=_err_response()),
        ):
            run_pipeline(_config(tmp_path, file_summarization=True))

        assert err.exists()

    def test_transcription_failure_does_not_remove_err(self, tmp_path):
        audio = tmp_path / "meeting.mp3"
        audio.touch()
        err = tmp_path / "meeting_err.txt"
        err.write_text("previous error", encoding="utf-8")

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_err_response()):
            run_pipeline(_config(tmp_path))

        assert err.exists()


class TestDirSummaryErrCleanup:
    # Patch at method level to avoid httpx.post conflicts between transcriber and summarizer
    # (both modules share the same httpx module object, so patching via either path
    # modifies the same attribute and the second patch wins).

    def test_dir_err_removed_after_dir_summary_success(self, tmp_path):
        audio = tmp_path / "meeting.mp3"
        audio.touch()
        dir_err = tmp_path / (tmp_path.name + "_err.txt")
        dir_err.write_text("previous dir error", encoding="utf-8")

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", return_value="transcript"),
            patch("whispercrawl.pipeline.summarizer.Summarizer.summarize_directory", return_value="dir summary"),
        ):
            run_pipeline(_config(tmp_path, dir_summarization=True))

        assert not dir_err.exists()

    def test_dir_err_written_on_dir_summary_failure(self, tmp_path):
        from whispercrawl.pipeline.summarizer import SummarizationError

        audio = tmp_path / "meeting.mp3"
        audio.touch()
        dir_err = tmp_path / (tmp_path.name + "_err.txt")

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", return_value="transcript"),
            patch(
                "whispercrawl.pipeline.summarizer.Summarizer.summarize_directory",
                side_effect=SummarizationError("dir failed"),
            ),
        ):
            run_pipeline(_config(tmp_path, dir_summarization=True))

        assert dir_err.exists()

    def test_no_dir_err_file_is_no_op(self, tmp_path):
        audio = tmp_path / "meeting.mp3"
        audio.touch()

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", return_value="transcript"),
            patch("whispercrawl.pipeline.summarizer.Summarizer.summarize_directory", return_value="dir summary"),
        ):
            run_pipeline(_config(tmp_path, dir_summarization=True))

        assert not (tmp_path / (tmp_path.name + "_err.txt")).exists()
