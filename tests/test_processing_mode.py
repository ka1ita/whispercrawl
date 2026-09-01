"""Tests for configurable processing order — per_file vs per_step (EPIC-042)."""

from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

from whispercrawl.config import (
    CleanupConfig,
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
from whispercrawl.pipeline.postprocessor import PostProcessingError
from whispercrawl.pipeline.transcriber import TranscriptionError


def _config(
    tmp_path: Path,
    *,
    processing_mode: str = "per_file",
    rescan: bool = False,
    max_files: int | None = None,
) -> Config:
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=rescan,
        processing_mode=processing_mode,
        max_files_per_run=max_files,
        state=StateConfig(enabled=True),
        formatter=FormatterConfig(format="txt"),
        transcription=TranscriptionConfig(output_suffix="", error_suffix="_err"),
        postprocessing=OllamaStepConfig(
            llm_enabled=True, regex_enabled=False, output_suffix="_fix"
        ),
        file_summarization=OllamaStepConfig(llm_enabled=True, output_suffix="_sum"),
        dir_summarization=DirSummarizationConfig(llm_enabled=False),
        schedule=ScheduleConfig(),
        cleanup=CleanupConfig(targets=[]),
        logging=LoggingConfig(),
    )


def _make_files(tmp_path: Path, names: list[str]) -> None:
    """Create media files with strictly increasing mtimes (names[-1] is newest)."""
    now = time.time()
    for i, name in enumerate(names):
        p = tmp_path / name
        p.write_bytes(b"\x00")
        os.utime(p, (now - (len(names) - i) * 100, now - (len(names) - i) * 100))


def _ok_transcribe(calls: list) :
    def fn(self, path: Path) -> str:
        calls.append(("transcribe", path.name))
        return f"t-{path.name}"
    return fn


def _ok_postprocess(calls: list):
    def fn(self, text: str, source_path: Path | None = None) -> str:
        calls.append(("postprocess", source_path.name))
        return f"fixed-{text}"
    return fn


def _ok_summarize(calls: list):
    def fn(self, text: str, file: str = "") -> str:
        calls.append(("summarize", file))
        return f"summary-{file}"
    return fn


def _patches(transcribe=None, postprocess=None, summarize=None):
    return (
        patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", transcribe),
        patch("whispercrawl.pipeline.postprocessor.PostProcessor.process", postprocess),
        patch("whispercrawl.pipeline.summarizer.Summarizer.summarize_file", summarize),
    )


class TestCallOrder:
    def test_per_file_interleaves_steps_per_file(self, tmp_path: Path):
        _make_files(tmp_path, ["a.mp3", "b.mp3"])
        calls: list = []
        p1, p2, p3 = _patches(
            _ok_transcribe(calls), _ok_postprocess(calls), _ok_summarize(calls),
        )
        with p1, p2, p3:
            run_pipeline(_config(tmp_path, processing_mode="per_file"))

        assert calls == [
            ("transcribe", "b.mp3"), ("postprocess", "b.mp3"), ("summarize", "b.mp3"),
            ("transcribe", "a.mp3"), ("postprocess", "a.mp3"), ("summarize", "a.mp3"),
        ]

    def test_per_step_batches_each_step_across_all_files(self, tmp_path: Path):
        _make_files(tmp_path, ["a.mp3", "b.mp3"])
        calls: list = []
        p1, p2, p3 = _patches(
            _ok_transcribe(calls), _ok_postprocess(calls), _ok_summarize(calls),
        )
        with p1, p2, p3:
            run_pipeline(_config(tmp_path, processing_mode="per_step"))

        assert calls == [
            ("transcribe", "b.mp3"), ("transcribe", "a.mp3"),
            ("postprocess", "b.mp3"), ("postprocess", "a.mp3"),
            ("summarize", "b.mp3"), ("summarize", "a.mp3"),
        ]


class TestPerStepFailureIsolation:
    def test_transcription_failure_excludes_only_that_file(self, tmp_path: Path):
        _make_files(tmp_path, ["a.mp3", "b.mp3"])
        calls: list = []

        def failing_transcribe(self, path: Path) -> str:
            calls.append(("transcribe", path.name))
            if path.name == "b.mp3":
                raise TranscriptionError("simulated failure")
            return f"t-{path.name}"

        p1, p2, p3 = _patches(
            failing_transcribe, _ok_postprocess(calls), _ok_summarize(calls),
        )
        with p1, p2, p3:
            run_pipeline(_config(tmp_path, processing_mode="per_step"))

        assert ("transcribe", "a.mp3") in calls
        assert ("transcribe", "b.mp3") in calls
        assert ("postprocess", "a.mp3") in calls
        assert ("summarize", "a.mp3") in calls
        assert ("postprocess", "b.mp3") not in calls
        assert ("summarize", "b.mp3") not in calls
        assert (tmp_path / "b_err.txt").exists()
        assert (tmp_path / "a.txt").exists()

    def test_postprocess_failure_does_not_prevent_summarization(self, tmp_path: Path):
        _make_files(tmp_path, ["a.mp3"])
        calls: list = []

        def failing_postprocess(self, text: str, source_path: Path | None = None) -> str:
            calls.append(("postprocess", source_path.name))
            raise PostProcessingError("simulated failure")

        p1, p2, p3 = _patches(
            _ok_transcribe(calls), failing_postprocess, _ok_summarize(calls),
        )
        with p1, p2, p3:
            run_pipeline(_config(tmp_path, processing_mode="per_step"))

        assert ("summarize", "a.mp3") in calls
        assert (tmp_path / "a_err.txt").exists()
        # a failed step → no consolidated result and no legacy sidecars
        assert not (tmp_path / "a.txt").exists()
        assert not (tmp_path / "a_sum.txt").exists()
        assert not (tmp_path / "a_fix.txt").exists()


class TestIdenticalOutput:
    def test_both_modes_produce_identical_output(self, tmp_path: Path):
        outputs = {}
        for mode in ("per_file", "per_step"):
            d = tmp_path / mode
            d.mkdir()
            _make_files(d, ["a.mp3", "b.mp3"])
            calls: list = []
            p1, p2, p3 = _patches(
                _ok_transcribe(calls), _ok_postprocess(calls), _ok_summarize(calls),
            )
            with p1, p2, p3:
                run_pipeline(_config(d, processing_mode=mode))
            # the per-directory result is named after the containing dir, which
            # differs per mode here; normalize that key so only content is compared
            outputs[mode] = {
                p.name.replace(mode, "<dir>"): p.read_text(encoding="utf-8")
                for p in sorted(d.glob("*.txt"))
            }

        assert outputs["per_file"] == outputs["per_step"]
        assert set(outputs["per_file"]) == {"a.txt", "b.txt", "<dir>.txt"}


class TestPerStepResume:
    def test_completed_transcribe_step_is_not_redone(self, tmp_path: Path):
        _make_files(tmp_path, ["a.mp3"])
        transcribe_calls: list = []

        def failing_postprocess(self, text: str, source_path: Path | None = None) -> str:
            raise PostProcessingError("simulated failure")

        p1, p2, p3 = _patches(
            _ok_transcribe(transcribe_calls), failing_postprocess, _ok_summarize([]),
        )
        with p1, p2, p3:
            run_pipeline(_config(tmp_path, processing_mode="per_step"))
        assert transcribe_calls == [("transcribe", "a.mp3")]

        p1, p2, p3 = _patches(
            _ok_transcribe(transcribe_calls), _ok_postprocess([]), _ok_summarize([]),
        )
        with p1, p2, p3:
            run_pipeline(_config(tmp_path, processing_mode="per_step"))
        assert transcribe_calls == [("transcribe", "a.mp3")]  # not called again
        assert (tmp_path / "a.txt").exists()  # consolidated result now complete


class TestMaxFilesPerRunUnderPerStep:
    def test_cap_bounds_a_single_run(self, tmp_path: Path):
        _make_files(tmp_path, ["a.mp3", "b.mp3"])
        calls: list = []
        p1, p2, p3 = _patches(
            _ok_transcribe(calls), _ok_postprocess(calls), _ok_summarize(calls),
        )
        with p1, p2, p3:
            run_pipeline(_config(tmp_path, processing_mode="per_step", max_files=1))
        assert calls == [("transcribe", "b.mp3"), ("postprocess", "b.mp3"), ("summarize", "b.mp3")]
        assert not (tmp_path / "a.txt").exists()

        calls.clear()
        with p1, p2, p3:
            run_pipeline(_config(tmp_path, processing_mode="per_step", max_files=1))
        assert calls == [("transcribe", "a.mp3"), ("postprocess", "a.mp3"), ("summarize", "a.mp3")]
