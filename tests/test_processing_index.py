"""Integration tests for the persisted processing index and max_files_per_run (EPIC-040)."""

from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

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
from whispercrawl.main import run_cleanup, run_pipeline
from whispercrawl.pipeline.postprocessor import PostProcessingError
from whispercrawl.pipeline.summarizer import SummarizationError
from whispercrawl.pipeline.transcriber import TranscriptionError


def _config(
    tmp_path: Path,
    *,
    rescan: bool = False,
    max_files: int | None = None,
) -> Config:
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=rescan,
        max_files_per_run=max_files,
        state=StateConfig(),
        formatter=FormatterConfig(format="txt"),
        transcription=TranscriptionConfig(output_suffix=""),
        postprocessing=OllamaStepConfig(llm_enabled=False, regex_enabled=False),
        file_summarization=OllamaStepConfig(llm_enabled=False),
        dir_summarization=DirSummarizationConfig(llm_enabled=False),
        schedule=ScheduleConfig(),
        logging=LoggingConfig(),
    )


def _transcripts(tmp_path: Path) -> set[str]:
    """Per-file result outputs, excluding the per-directory consolidated result."""
    return {p.name for p in tmp_path.glob("*.txt") if p.stem != tmp_path.name}


def _has_error(tmp_path: Path, rel: str) -> bool:
    """True when the processing index holds a failure row for ``rel`` (EPIC-049)."""
    from whispercrawl.state import ProcessingState

    with ProcessingState.open(tmp_path / "db" / "state.db") as st:
        return bool(st.get_errors(rel))


def _make_files(tmp_path: Path, names: list[str]) -> None:
    """Create media files with strictly increasing mtimes (names[-1] is newest)."""
    now = time.time()
    for i, name in enumerate(names):
        p = tmp_path / name
        p.write_bytes(b"\x00")
        os.utime(p, (now - (len(names) - i) * 100, now - (len(names) - i) * 100))


def _run(cfg: Config, fail_on: set[str] | None = None) -> list[str]:
    """Run the pipeline with a stubbed transcriber; return processed file names in order."""
    fail_on = fail_on or set()
    processed: list[str] = []

    def fake_transcribe(self, path: Path) -> str:
        processed.append(path.name)
        if path.name in fail_on:
            raise TranscriptionError("simulated failure")
        return f"transcript for {path.name}"

    with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", fake_transcribe):
        run_pipeline(cfg)
    return processed


class TestMaxFilesPerRun:
    def test_cap_limits_one_run_then_next_run_finishes(self, tmp_path: Path):
        _make_files(tmp_path, ["a.mp3", "b.mp3", "c.mp3", "d.mp3", "e.mp3"])

        first = _run(_config(tmp_path, max_files=2))
        assert first == ["e.mp3", "d.mp3"]  # newest first
        assert _transcripts(tmp_path) == {"d.txt", "e.txt"}

        second = _run(_config(tmp_path, max_files=2))
        assert second == ["c.mp3", "b.mp3"]

        third = _run(_config(tmp_path, max_files=2))
        assert third == ["a.mp3"]

        fourth = _run(_config(tmp_path, max_files=2))
        assert fourth == []
        assert len(_transcripts(tmp_path)) == 5


class TestResumability:
    def test_interrupted_run_resumes_without_redoing_completed(self, tmp_path: Path):
        _make_files(tmp_path, ["a.mp3", "b.mp3", "c.mp3", "d.mp3", "e.mp3"])
        # newest-first order: e, d, c, b, a — fail on the 3rd (c)
        first = _run(_config(tmp_path), fail_on={"c.mp3"})
        assert first == ["e.mp3", "d.mp3", "c.mp3", "b.mp3", "a.mp3"]
        assert _has_error(tmp_path, "c.mp3")
        assert not (tmp_path / "c_err.txt").exists()

        # second run: e and d are done → not re-transcribed; c retried, plus b/a already have .txt
        second = _run(_config(tmp_path))
        assert "e.mp3" not in second
        assert "d.mp3" not in second
        assert "c.mp3" in second

    def test_error_file_reprocessed_until_it_succeeds(self, tmp_path: Path):
        _make_files(tmp_path, ["x.mp3"])
        _run(_config(tmp_path), fail_on={"x.mp3"})
        assert not (tmp_path / "x.txt").exists()

        second = _run(_config(tmp_path))  # no longer failing
        assert second == ["x.mp3"]
        assert (tmp_path / "x.txt").exists()


class TestCleanupClearsIndex:
    def test_cleanup_clears_state_so_files_reprocess(self, tmp_path: Path):
        _make_files(tmp_path, ["a.mp3", "b.mp3"])
        _run(_config(tmp_path))
        assert len(_transcripts(tmp_path)) == 2

        cfg = _config(tmp_path)
        run_cleanup(cfg)
        assert list(tmp_path.glob("*.txt")) == []
        # the state.db file may remain on disk; its rows must have been cleared

        again = _run(_config(tmp_path))
        assert sorted(again) == ["a.mp3", "b.mp3"]


class TestStepResume:
    """EPIC-041: an interrupted file resumes from its last completed step."""

    def test_resume_after_postprocess_failure_does_not_retranscribe(self, tmp_path: Path):
        _make_files(tmp_path, ["a.mp3"])
        cfg = _config(tmp_path)
        cfg.postprocessing = OllamaStepConfig(
            llm_enabled=True, regex_enabled=False, output_suffix="_fix",
        )

        transcribe_calls: list[str] = []
        postprocess_calls: list[str] = []

        def fake_transcribe(self, path: Path) -> str:
            transcribe_calls.append(path.name)
            return f"transcript for {path.name}"

        def failing_postprocess(self, text: str, source_path: Path | None = None) -> str:
            postprocess_calls.append(source_path.name)
            raise PostProcessingError("simulated failure")

        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", fake_transcribe), \
             patch(
                 "whispercrawl.pipeline.postprocessor.PostProcessor.process", failing_postprocess,
             ):
            run_pipeline(cfg)

        assert transcribe_calls == ["a.mp3"]
        assert postprocess_calls == ["a.mp3"]
        # a failed step → nothing beside the audio; the failure is in the index
        assert not (tmp_path / "a.txt").exists()
        assert not (tmp_path / "a_fix.txt").exists()
        assert not (tmp_path / "a_err.txt").exists()
        assert _has_error(tmp_path, "a.mp3")

        def ok_postprocess(self, text: str, source_path: Path | None = None) -> str:
            postprocess_calls.append(source_path.name)
            return f"fixed {text}"

        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", fake_transcribe), \
             patch("whispercrawl.pipeline.postprocessor.PostProcessor.process", ok_postprocess):
            run_pipeline(cfg)

        assert transcribe_calls == ["a.mp3"]  # not called again — resumed from the index
        assert postprocess_calls == ["a.mp3", "a.mp3"]
        assert (tmp_path / "a.txt").exists()  # consolidated result now complete
        assert not (tmp_path / "a_fix.txt").exists()

    def test_resume_after_summarize_failure_does_not_repostprocess(self, tmp_path: Path):
        _make_files(tmp_path, ["a.mp3"])
        cfg = _config(tmp_path)
        cfg.postprocessing = OllamaStepConfig(
            llm_enabled=True, regex_enabled=False, output_suffix="_fix",
        )
        cfg.file_summarization = OllamaStepConfig(llm_enabled=True, output_suffix="_sum")

        transcribe_calls: list[str] = []
        postprocess_calls: list[str] = []
        summarize_calls: list[str] = []

        def fake_transcribe(self, path: Path) -> str:
            transcribe_calls.append(path.name)
            return f"transcript for {path.name}"

        def ok_postprocess(self, text: str, source_path: Path | None = None) -> str:
            postprocess_calls.append(source_path.name)
            return f"fixed {text}"

        def failing_summarize(self, text: str, file: str = "") -> str:
            summarize_calls.append(file)
            raise SummarizationError("simulated failure")

        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", fake_transcribe), \
             patch("whispercrawl.pipeline.postprocessor.PostProcessor.process", ok_postprocess), \
             patch("whispercrawl.pipeline.summarizer.Summarizer.summarize_file", failing_summarize):
            run_pipeline(cfg)

        assert transcribe_calls == ["a.mp3"]
        assert postprocess_calls == ["a.mp3"]
        assert summarize_calls == ["a.mp3"]
        assert not (tmp_path / "a_sum.txt").exists()
        assert not (tmp_path / "a.txt").exists()

        def ok_summarize(self, text: str, file: str = "") -> str:
            summarize_calls.append(file)
            return f"summary of {file}"

        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", fake_transcribe), \
             patch("whispercrawl.pipeline.postprocessor.PostProcessor.process", ok_postprocess), \
             patch("whispercrawl.pipeline.summarizer.Summarizer.summarize_file", ok_summarize):
            run_pipeline(cfg)

        assert transcribe_calls == ["a.mp3"]      # not re-run
        assert postprocess_calls == ["a.mp3"]     # not re-run (stored fixed text reused)
        assert summarize_calls == ["a.mp3", "a.mp3"]
        assert (tmp_path / "a.txt").exists()

    def test_source_file_change_between_attempts_discards_recorded_step(self, tmp_path: Path):
        _make_files(tmp_path, ["a.mp3"])
        cfg = _config(tmp_path)
        cfg.postprocessing = OllamaStepConfig(
            llm_enabled=True, regex_enabled=False, output_suffix="_fix",
        )

        transcribe_calls: list[str] = []

        def fake_transcribe(self, path: Path) -> str:
            transcribe_calls.append(path.name)
            return f"transcript for {path.name}"

        def failing_postprocess(self, text: str, source_path: Path | None = None) -> str:
            raise PostProcessingError("simulated failure")

        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", fake_transcribe), \
             patch(
                 "whispercrawl.pipeline.postprocessor.PostProcessor.process", failing_postprocess,
             ):
            run_pipeline(cfg)
        assert transcribe_calls == ["a.mp3"]

        # source file changes between attempts — recorded "transcribe" step must be discarded
        source = tmp_path / "a.mp3"
        source.write_bytes(b"\x01\x02\x03")
        os.utime(source, (time.time(), time.time()))

        def ok_postprocess(self, text: str, source_path: Path | None = None) -> str:
            return f"fixed {text}"

        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", fake_transcribe), \
             patch("whispercrawl.pipeline.postprocessor.PostProcessor.process", ok_postprocess):
            run_pipeline(cfg)

        assert transcribe_calls == ["a.mp3", "a.mp3"]  # re-transcribed, not resumed


class TestStateAlwaysOn:
    def test_index_created_and_second_run_skips(self, tmp_path: Path):
        _make_files(tmp_path, ["a.mp3", "b.mp3"])
        first = _run(_config(tmp_path))
        assert sorted(first) == ["a.mp3", "b.mp3"]
        assert (tmp_path / "db" / "state.db").exists()

        second = _run(_config(tmp_path))
        assert second == []

    def test_dry_run_creates_no_db(self, tmp_path: Path):
        _make_files(tmp_path, ["a.mp3"])
        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", lambda self, p: "t"):
            run_pipeline(_config(tmp_path), dry_run=True)
        assert not (tmp_path / "db").exists()
