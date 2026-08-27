"""Integration tests for the persisted processing index and max_files_per_run (EPIC-040)."""

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
from whispercrawl.main import run_cleanup, run_pipeline
from whispercrawl.pipeline.transcriber import TranscriptionError


def _config(
    tmp_path: Path,
    *,
    rescan: bool = False,
    max_files: int | None = None,
    state_enabled: bool = True,
) -> Config:
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=rescan,
        max_files_per_run=max_files,
        state=StateConfig(enabled=state_enabled),
        formatter=FormatterConfig(format="txt"),
        transcription=TranscriptionConfig(output_suffix="", error_suffix="_err"),
        postprocessing=OllamaStepConfig(llm_enabled=False, regex_enabled=False),
        file_summarization=OllamaStepConfig(llm_enabled=False),
        dir_summarization=DirSummarizationConfig(llm_enabled=False),
        schedule=ScheduleConfig(),
        cleanup=CleanupConfig(targets=[]),
        logging=LoggingConfig(),
    )


def _transcripts(tmp_path: Path) -> set[str]:
    """Per-file transcript outputs, excluding the per-directory _concat.txt."""
    return {p.name for p in tmp_path.glob("*.txt") if not p.stem.endswith("_concat")}


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
        assert (tmp_path / "c_err.txt").exists()

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
        cfg.cleanup = CleanupConfig(targets=["", "_concat"])
        run_cleanup(cfg)
        assert list(tmp_path.glob("*.txt")) == []
        # the state.db file may remain on disk; its rows must have been cleared

        again = _run(_config(tmp_path))
        assert sorted(again) == ["a.mp3", "b.mp3"]


class TestStateDisabled:
    def test_disabled_creates_no_db_and_still_skips_via_outputs(self, tmp_path: Path):
        _make_files(tmp_path, ["a.mp3", "b.mp3"])
        first = _run(_config(tmp_path, state_enabled=False))
        assert sorted(first) == ["a.mp3", "b.mp3"]
        assert not (tmp_path / ".whispercrawl").exists()

        # second run: outputs exist → skipped by the output-existence check
        second = _run(_config(tmp_path, state_enabled=False))
        assert second == []

    def test_dry_run_creates_no_db(self, tmp_path: Path):
        _make_files(tmp_path, ["a.mp3"])
        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", lambda self, p: "t"):
            run_pipeline(_config(tmp_path), dry_run=True)
        assert not (tmp_path / ".whispercrawl").exists()
