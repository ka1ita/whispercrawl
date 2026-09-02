"""EPIC-055: an unexpected exception in one step/file must not abort the run.

Any exception (not just the typed pipeline errors) is caught, recorded in the
processing index, and the run continues with the next file.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from whispercrawl.config import (
    Config,
    DirSummarizationConfig,
    FormatterConfig,
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


def _config(tmp_path: Path, *, fmt: str = "txt", dir_summarization: bool = False) -> Config:
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=True,
        state=StateConfig(),
        transcription=TranscriptionConfig(output_suffix=""),
        postprocessing=OllamaStepConfig(llm_enabled=False, regex_enabled=False),
        file_summarization=OllamaStepConfig(llm_enabled=False),
        dir_summarization=DirSummarizationConfig(llm_enabled=dir_summarization),
        formatter=FormatterConfig(enabled=fmt != "txt", format=fmt),
        schedule=ScheduleConfig(),
        logging=LoggingConfig(),
    )


def _errors(tmp_path: Path, rel: str | None = None):
    with ProcessingState.open(tmp_path / "db" / "state.db") as st:
        return st.get_errors(rel)


def _status(tmp_path: Path, rel: str):
    with ProcessingState.open(tmp_path / "db" / "state.db") as st:
        rec = st.lookup(rel)
        return rec.status if rec else None


class TestTranscribeCrashIsContained:
    def test_bare_oserror_from_one_file_does_not_abort_the_batch(self, tmp_path):
        (tmp_path / "a.mp3").touch()
        (tmp_path / "b.mp3").touch()

        real_open = open

        def fake_open(path, *args, **kwargs):
            if str(path).endswith("a.mp3"):
                raise FileNotFoundError(2, "No such file or directory", str(path))
            return real_open(path, *args, **kwargs)

        with (
            patch("whispercrawl.pipeline.transcriber.open", fake_open, create=True),
            patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_ok_response()),
        ):
            run_pipeline(_config(tmp_path))  # must not raise

        assert [r.step for r in _errors(tmp_path, "a.mp3")] == ["transcribe"]
        assert _status(tmp_path, "a.mp3") == "error"
        assert not (tmp_path / "a.txt").exists()
        # the second file was still processed
        assert (tmp_path / "b.txt").exists()
        assert _status(tmp_path, "b.mp3") == "done"

    def test_unexpected_exception_type_is_still_contained(self, tmp_path):
        (tmp_path / "a.mp3").touch()
        (tmp_path / "b.mp3").touch()

        def transcribe(self, file_path):
            if file_path.name == "a.mp3":
                raise RuntimeError("something completely unexpected")
            return "transcript b"

        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", transcribe):
            run_pipeline(_config(tmp_path))

        assert [r.step for r in _errors(tmp_path, "a.mp3")] == ["transcribe"]
        assert (tmp_path / "b.txt").exists()


class TestFinalizeCrashIsContained:
    def test_oserror_writing_result_records_finalize_row(self, tmp_path):
        (tmp_path / "a.mp3").touch()
        (tmp_path / "b.mp3").touch()

        real_write = Path.write_text

        def fake_write(self, *args, **kwargs):
            if self.name == "a.txt":
                raise OSError("No space left on device")
            return real_write(self, *args, **kwargs)

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", return_value="t"),
            patch.object(Path, "write_text", fake_write),
        ):
            run_pipeline(_config(tmp_path))

        assert [r.step for r in _errors(tmp_path, "a.mp3")] == ["finalize"]
        assert _status(tmp_path, "a.mp3") == "error"
        assert not (tmp_path / "a.txt").exists()
        assert (tmp_path / "b.txt").exists()


class TestFormatCrashIsContained:
    def test_one_bad_format_does_not_skip_the_rest(self, tmp_path):
        (tmp_path / "a.mp3").touch()
        (tmp_path / "b.mp3").touch()

        from whispercrawl.pipeline.formatter import Formatter

        real_format = Formatter.format_file

        def fake_format(self, path):
            if path.name == "a.txt":
                raise ValueError("bad content")
            return real_format(self, path)

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", return_value="t"),
            patch.object(Formatter, "format_file", fake_format),
        ):
            run_pipeline(_config(tmp_path, fmt="md"))

        assert [r.step for r in _errors(tmp_path, "a.txt")] == ["format"]
        # b was still formatted
        assert (tmp_path / "b.md").exists()


class TestDirLoopCrashIsContained:
    def test_failure_in_one_dir_does_not_abort_the_rest(self, tmp_path):
        d1 = tmp_path / "d1"
        d2 = tmp_path / "d2"
        d1.mkdir()
        d2.mkdir()
        (d1 / "x.mp3").touch()
        (d2 / "y.mp3").touch()

        from whispercrawl.pipeline.summarizer import Summarizer

        real_concat = Summarizer.concat_transcriptions

        def fake_concat(self, selected):
            if any(k.startswith("x") for k in selected):
                raise RuntimeError("concat blew up unexpectedly")
            return real_concat(self, selected)

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", return_value="t"),
            patch.object(Summarizer, "concat_transcriptions", fake_concat),
        ):
            run_pipeline(_config(tmp_path))

        rows = _errors(tmp_path, "d1")
        assert [(r.scope, r.step) for r in rows] == [("dir", "dir_finalize")]
        # the other directory's result was still written
        assert (tmp_path / "d2" / "d2.txt").exists()


class TestKeyboardInterruptStillPropagates:
    def test_ctrl_c_during_transcribe_aborts_and_records_partial(self, tmp_path):
        (tmp_path / "a.mp3").touch()

        with patch(
            "whispercrawl.pipeline.transcriber.Transcriber.transcribe",
            side_effect=KeyboardInterrupt,
        ):
            with pytest.raises(KeyboardInterrupt):
                run_pipeline(_config(tmp_path))

        assert _status(tmp_path, "a.mp3") == "partial"
