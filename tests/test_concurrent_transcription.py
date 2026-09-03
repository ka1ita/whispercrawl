"""Integration tests for concurrent multi-engine transcription (EPIC-056)."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

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
from asr_crawler.main import run_pipeline
from asr_crawler.pipeline.transcriber import TranscriptionError
from asr_crawler.state import ProcessingState


def _config(tmp_path: Path, engine_names, *, concurrency=1, fmt="txt",
            mode="per_file", rescan=True) -> Config:
    base = TranscriptionConfig(output_suffix="", diarize=False, concurrency=concurrency)
    base.engines = [TranscriptionConfig(name=n, diarize=False) for n in engine_names]
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=rescan,
        processing_mode=mode,
        state=StateConfig(),
        formatter=FormatterConfig(format=fmt),
        transcription=base,
        postprocessing=OllamaStepConfig(llm_enabled=False, regex_enabled=False),
        file_summarization=OllamaStepConfig(llm_enabled=False),
        dir_summarization=DirSummarizationConfig(llm_enabled=False),
        schedule=ScheduleConfig(),
        logging=LoggingConfig(),
    )


def _errors(tmp_path: Path, rel: str | None = None):
    with ProcessingState.open(tmp_path / "db" / "state.db") as idx:
        return idx.get_errors(rel)


def _by_engine(self, path: Path) -> str:
    return f"{self.config.name}::{path.name}"


class TestSequentialWhenConcurrencyIsOne:
    def test_no_thread_pool_constructed(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")
        with patch("asr_crawler.main.ThreadPoolExecutor") as pool, \
             patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe", _by_engine):
            run_pipeline(_config(tmp_path, ["a", "b"], concurrency=1))
        pool.assert_not_called()

    def test_single_engine_never_uses_pool(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")
        with patch("asr_crawler.main.ThreadPoolExecutor") as pool, \
             patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe",
                   lambda self, p: "plain"):
            cfg = _config(tmp_path, [], concurrency=8)
            cfg.transcription.engines = [TranscriptionConfig(name="", diarize=False)]
            run_pipeline(cfg)
        pool.assert_not_called()
        assert (tmp_path / "rec.txt").read_text(encoding="utf-8") == "plain"


class TestOutputIdenticalAcrossConcurrency:
    def _run(self, tmp_path: Path, concurrency: int, mode: str) -> dict:
        dname = f"{mode}-{concurrency}"
        d = tmp_path / dname
        d.mkdir()
        for n in ("a", "b", "c"):
            (d / f"{n}.mp3").write_bytes(b"\x00")
        with patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe", _by_engine):
            run_pipeline(_config(d, ["x", "y"], concurrency=concurrency, mode=mode))
        results = {
            p.name.replace(dname, "<d>"): p.read_text(encoding="utf-8")
            for p in sorted(d.glob("*.txt"))
        }
        st = (d / "a.mp3").stat()
        with ProcessingState.open(d / "db" / "state.db") as idx:
            for eng in ("x", "y"):
                results[f"idx:a:{eng}"] = idx.get_text("a.mp3", "asr", st.st_mtime, st.st_size, eng)
        return results

    def test_per_file(self, tmp_path):
        assert self._run(tmp_path, 1, "per_file") == self._run(tmp_path, 3, "per_file")

    def test_per_step(self, tmp_path):
        assert self._run(tmp_path, 1, "per_step") == self._run(tmp_path, 3, "per_step")


class TestParallelism:
    def test_engines_overlap_in_time(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")
        delay = 0.4

        def slow(self, path: Path) -> str:
            time.sleep(delay)
            return f"{self.config.name}::{path.name}"

        with patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe", slow):
            start = time.monotonic()
            run_pipeline(_config(tmp_path, ["a", "b", "c"], concurrency=3))
            elapsed = time.monotonic() - start

        assert elapsed < delay * 2  # ~delay, not ~3*delay
        assert (tmp_path / "rec_a.txt").exists()
        assert (tmp_path / "rec_c.txt").exists()

    def test_per_step_bounds_in_flight_calls(self, tmp_path):
        for n in ("a", "b", "c", "d"):
            (tmp_path / f"{n}.mp3").write_bytes(b"\x00")

        lock = threading.Lock()
        state = {"cur": 0, "max": 0}

        def tracked(self, path: Path) -> str:
            with lock:
                state["cur"] += 1
                state["max"] = max(state["max"], state["cur"])
            time.sleep(0.1)
            with lock:
                state["cur"] -= 1
            return f"{self.config.name}::{path.name}"

        with patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe", tracked):
            run_pipeline(_config(tmp_path, ["x", "y"], concurrency=3, mode="per_step"))

        assert state["max"] <= 3
        assert state["max"] > 1  # actually overlapped


class TestFailureIsolationUnderThreading:
    def test_one_engine_error_leaves_the_other_intact(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        def fail_b(self, path: Path) -> str:
            if self.config.name == "b":
                raise TranscriptionError("boom")
            return f"a::{path.name}"

        with patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe", fail_b):
            run_pipeline(_config(tmp_path, ["a", "b"], concurrency=2, rescan=False))

        assert (tmp_path / "rec_a.txt").read_text(encoding="utf-8") == "a::rec.mp3"
        assert not (tmp_path / "rec_b.txt").exists()
        assert [(e.engine, e.step) for e in _errors(tmp_path, "rec.mp3")] == [("b", "transcribe")]
        with ProcessingState.open(tmp_path / "db" / "state.db") as idx:
            assert idx.lookup("rec.mp3").status == "error"

    def test_bare_exception_from_one_engine_is_contained(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        def fail_b(self, path: Path) -> str:
            if self.config.name == "b":
                raise RuntimeError("unexpected")
            return f"a::{path.name}"

        with patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe", fail_b):
            run_pipeline(_config(tmp_path, ["a", "b"], concurrency=2, rescan=False))

        assert (tmp_path / "rec_a.txt").exists()
        errs = _errors(tmp_path, "rec.mp3")
        assert [(e.engine, e.step) for e in errs] == [("b", "transcribe")]
        assert "RuntimeError" in errs[0].message


class TestInterrupt:
    def test_keyboardinterrupt_from_engine_propagates_and_records_partial(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")

        def boom(self, path: Path) -> str:
            if self.config.name == "b":
                raise KeyboardInterrupt
            return f"a::{path.name}"

        with patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe", boom):
            with pytest.raises(KeyboardInterrupt):
                run_pipeline(_config(tmp_path, ["a", "b"], concurrency=2, rescan=False))

        with ProcessingState.open(tmp_path / "db" / "state.db") as idx:
            assert idx.lookup("rec.mp3").status == "partial"


class TestRefreshIgnoresConcurrency:
    def test_refresh_does_not_construct_a_pool(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")
        cfg = _config(tmp_path, ["a", "b"], concurrency=4, rescan=False)
        with patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe", _by_engine):
            run_pipeline(cfg)

        def boom(self, p):
            raise AssertionError("must not transcribe during --refresh")

        with patch("asr_crawler.main.ThreadPoolExecutor") as pool, \
             patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe", boom):
            run_pipeline(cfg, refresh=True)
        pool.assert_not_called()
        assert (tmp_path / "rec_a.txt").exists()
        assert (tmp_path / "rec_b.txt").exists()
