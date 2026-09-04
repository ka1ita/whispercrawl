"""EPIC-058: stop (and stay stopped) after too many consecutive file failures.

``max_error_count`` parks the pipeline once the cross-run failure counter reaches
the limit; a fully-successful file resets it, and ``asr-crawler --reset-errors``
clears it by hand.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from asr_crawler.config import (
    Config,
    DirSummarizationConfig,
    FormatterConfig,
    LoggingConfig,
    OllamaStepConfig,
    ScheduleConfig,
    StateConfig,
    TranscriptionConfig,
)
from asr_crawler.main import run_pipeline, run_reset_errors
from asr_crawler.pipeline.transcriber import TranscriptionError
from asr_crawler.state import ProcessingState

DB = ("db", "state.db")


def _config(tmp_path: Path, *, max_error_count=None, engine_names=None, mode="per_file") -> Config:
    base = TranscriptionConfig(output_suffix="", diarize=False)
    if engine_names:
        base.engines = [TranscriptionConfig(name=n, diarize=False) for n in engine_names]
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=True,
        processing_mode=mode,
        max_error_count=max_error_count,
        state=StateConfig(),
        transcription=base,
        postprocessing=OllamaStepConfig(llm_enabled=False, regex_enabled=False),
        file_summarization=OllamaStepConfig(llm_enabled=False),
        dir_summarization=DirSummarizationConfig(llm_enabled=False),
        formatter=FormatterConfig(enabled=False, format="txt"),
        schedule=ScheduleConfig(),
        logging=LoggingConfig(),
    )


def _state(tmp_path: Path) -> ProcessingState:
    return ProcessingState.open(tmp_path.joinpath(*DB))


def _make_files(tmp_path: Path, n: int) -> None:
    for i in range(n):
        (tmp_path / f"{i:02d}.mp3").write_bytes(b"\x00")


def _always_fail(self, path: Path):
    raise TranscriptionError("service down")


class TestBrakeTrips:
    def test_stops_after_limit_and_leaves_rest_untouched(self, tmp_path):
        _make_files(tmp_path, 5)
        with patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe", _always_fail):
            run_pipeline(_config(tmp_path, max_error_count=3))  # must not raise

        with _state(tmp_path) as st:
            assert st.get_error_count() == 3
            failed_paths = {e.path for e in st.get_errors()}
            assert len(failed_paths) == 3
            # exactly three files reached the index; the other two were never touched
            rows = st._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            assert rows == 3

    def test_successful_file_resets_the_streak(self, tmp_path):
        _make_files(tmp_path, 5)

        def transcribe(self, path: Path):
            if path.name == "02.mp3":
                return "ok"
            raise TranscriptionError("service down")

        with patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe", transcribe):
            run_pipeline(_config(tmp_path, max_error_count=3))

        # 00,01 fail (count 2) -> 02 ok (reset) -> 03,04 fail (count 2): never trips
        with _state(tmp_path) as st:
            assert st.get_error_count() == 2
            assert st._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 5
        assert (tmp_path / "02.txt").exists()

    def test_multi_engine_failure_counts_once_per_file(self, tmp_path):
        _make_files(tmp_path, 1)
        with patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe", _always_fail):
            run_pipeline(_config(tmp_path, max_error_count=5, engine_names=["a", "b"]))

        with _state(tmp_path) as st:
            assert st.get_error_count() == 1


class TestBrakeStaysTripped:
    def test_pretripped_index_short_circuits_then_reset_resumes(self, tmp_path):
        _make_files(tmp_path, 2)
        with _state(tmp_path) as st:
            st._set_error_count(5)

        # a working transcriber — but the brake is already tripped
        with patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe", return_value="ok"):
            run_pipeline(_config(tmp_path, max_error_count=3))
        assert not (tmp_path / "00.txt").exists()
        with _state(tmp_path) as st:
            assert st.get_error_count() == 5

        assert run_reset_errors(_config(tmp_path, max_error_count=3)) == 0
        with _state(tmp_path) as st:
            assert st.get_error_count() == 0

        with patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe", return_value="ok"):
            run_pipeline(_config(tmp_path, max_error_count=3))
        assert (tmp_path / "00.txt").exists()
        assert (tmp_path / "01.txt").exists()

    def test_reset_errors_leaves_recorded_error_rows_intact(self, tmp_path):
        _make_files(tmp_path, 3)
        with patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe", _always_fail):
            run_pipeline(_config(tmp_path, max_error_count=2))

        run_reset_errors(_config(tmp_path, max_error_count=2))
        with _state(tmp_path) as st:
            assert st.get_error_count() == 0
            assert len(st.get_errors()) >= 2  # error rows untouched

    def test_reset_errors_without_index_is_a_noop(self, tmp_path):
        assert run_reset_errors(_config(tmp_path, max_error_count=2)) == 0


class TestDisabledAndDryRun:
    def test_disabled_by_default_never_counts(self, tmp_path):
        _make_files(tmp_path, 3)
        with patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe", _always_fail):
            run_pipeline(_config(tmp_path))  # max_error_count=None

        with _state(tmp_path) as st:
            assert st.get_error_count() == 0
            # every file was still attempted
            assert st._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 3

    def test_dry_run_does_not_touch_the_counter(self, tmp_path):
        _make_files(tmp_path, 2)
        with _state(tmp_path) as st:
            st._set_error_count(9)

        run_pipeline(_config(tmp_path, max_error_count=3), dry_run=True)

        with _state(tmp_path) as st:
            assert st.get_error_count() == 9
