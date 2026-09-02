"""Failures are recorded in the processing index, not in _err.txt sidecars (EPIC-049)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from whispercrawl.config import (
    Config,
    DirSummarizationConfig,
    LoggingConfig,
    OllamaStepConfig,
    ScheduleConfig,
    StateConfig,
    TranscriptionConfig,
)
from whispercrawl.main import run_pipeline
from whispercrawl.state import ProcessingState


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


def _config(
    tmp_path: Path,
    *,
    postprocessing=False,
    file_summarization=False,
    dir_summarization=False,
) -> Config:
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=True,
        state=StateConfig(),
        transcription=TranscriptionConfig(output_suffix=""),
        postprocessing=OllamaStepConfig(llm_enabled=postprocessing, regex_enabled=False),
        file_summarization=OllamaStepConfig(llm_enabled=file_summarization, output_suffix="_sum"),
        dir_summarization=DirSummarizationConfig(llm_enabled=dir_summarization, output_suffix="_sum"),
        schedule=ScheduleConfig(),
        logging=LoggingConfig(),
    )


def _errors(tmp_path: Path, rel: str | None = None):
    with ProcessingState.open(tmp_path / "db" / "state.db") as st:
        return st.get_errors(rel)


class TestPerFileErrors:
    def test_no_sidecar_and_row_cleared_after_full_success(self, tmp_path):
        (tmp_path / "meeting.mp3").touch()

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response()):
            run_pipeline(_config(tmp_path))

        assert not (tmp_path / "meeting_err.txt").exists()
        assert (tmp_path / "meeting.txt").exists()
        assert _errors(tmp_path) == []

    def test_postprocessing_failure_records_row_no_sidecar(self, tmp_path):
        from whispercrawl.pipeline.postprocessor import PostProcessingError

        (tmp_path / "meeting.mp3").touch()

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", return_value="transcript"),
            patch(
                "whispercrawl.pipeline.postprocessor.PostProcessor.process",
                side_effect=PostProcessingError("boom"),
            ),
        ):
            run_pipeline(_config(tmp_path, postprocessing=True))

        assert not (tmp_path / "meeting_err.txt").exists()
        rows = _errors(tmp_path, "meeting.mp3")
        assert [r.step for r in rows] == ["postprocess"]
        assert rows[0].scope == "file"

    def test_file_summarization_failure_records_row(self, tmp_path):
        from whispercrawl.pipeline.summarizer import SummarizationError

        (tmp_path / "meeting.mp3").touch()

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", return_value="transcript"),
            patch(
                "whispercrawl.pipeline.summarizer.Summarizer.summarize_file",
                side_effect=SummarizationError("boom"),
            ),
        ):
            run_pipeline(_config(tmp_path, file_summarization=True))

        assert not (tmp_path / "meeting_err.txt").exists()
        assert [r.step for r in _errors(tmp_path, "meeting.mp3")] == ["file_summarize"]

    def test_transcription_failure_records_row(self, tmp_path):
        (tmp_path / "meeting.mp3").touch()

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_err_response()):
            run_pipeline(_config(tmp_path))

        assert not (tmp_path / "meeting_err.txt").exists()
        assert [r.step for r in _errors(tmp_path, "meeting.mp3")] == ["transcribe"]

    def test_fixing_the_failure_clears_the_row(self, tmp_path):
        from whispercrawl.pipeline.postprocessor import PostProcessingError

        (tmp_path / "meeting.mp3").touch()
        cfg = _config(tmp_path, postprocessing=True)

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", return_value="transcript"),
            patch(
                "whispercrawl.pipeline.postprocessor.PostProcessor.process",
                side_effect=PostProcessingError("boom"),
            ),
        ):
            run_pipeline(cfg)
        assert _errors(tmp_path, "meeting.mp3")

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", return_value="transcript"),
            patch("whispercrawl.pipeline.postprocessor.PostProcessor.process", return_value="fixed"),
        ):
            run_pipeline(cfg)

        assert _errors(tmp_path, "meeting.mp3") == []
        assert (tmp_path / "meeting.txt").exists()



class TestOnceCleanup:
    def test_success_then_cleanup_removes_the_result(self, tmp_path):
        (tmp_path / "meeting.mp3").touch()

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response()):
            run_pipeline(_config(tmp_path), cleanup=True)

        # --once --cleanup deletes the result it just produced (success gate met).
        assert not (tmp_path / "meeting.txt").exists()
        assert _errors(tmp_path) == []

    def test_failed_file_has_nothing_to_clean_and_no_sidecar(self, tmp_path):
        from whispercrawl.pipeline.postprocessor import PostProcessingError

        (tmp_path / "meeting.mp3").touch()

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", return_value="transcript"),
            patch(
                "whispercrawl.pipeline.postprocessor.PostProcessor.process",
                side_effect=PostProcessingError("boom"),
            ),
        ):
            run_pipeline(_config(tmp_path, postprocessing=True), cleanup=True)

        assert not (tmp_path / "meeting.txt").exists()
        assert not (tmp_path / "meeting_err.txt").exists()
        assert [r.step for r in _errors(tmp_path, "meeting.mp3")] == ["postprocess"]


class TestDirErrors:
    def test_dir_summary_success_leaves_no_row_or_sidecar(self, tmp_path):
        (tmp_path / "meeting.mp3").touch()

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", return_value="transcript"),
            patch("whispercrawl.pipeline.summarizer.Summarizer.summarize_file", return_value="dir summary"),
        ):
            run_pipeline(_config(tmp_path, dir_summarization=True))

        assert not (tmp_path / (tmp_path.name + "_err.txt")).exists()
        assert _errors(tmp_path) == []

    def test_dir_summary_failure_records_dir_scoped_row(self, tmp_path):
        from whispercrawl.pipeline.summarizer import SummarizationError

        (tmp_path / "meeting.mp3").touch()

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", return_value="transcript"),
            patch(
                "whispercrawl.pipeline.summarizer.Summarizer.concat_transcriptions",
                side_effect=SummarizationError("dir failed"),
            ),
        ):
            run_pipeline(_config(tmp_path, dir_summarization=True))

        assert not (tmp_path / (tmp_path.name + "_err.txt")).exists()
        rows = _errors(tmp_path, ".")
        assert [(r.scope, r.step) for r in rows] == [("dir", "dir_summarize")]
