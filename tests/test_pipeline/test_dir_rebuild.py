"""Integration tests for the directory-result rebuild (EPIC-059).

A directory result covers **every current file in the directory** — this run's
in-memory texts plus the stored ``asr``/``fixed`` text of the already-done
files — instead of being overwritten with whatever subset the current run
happened to process.
"""

from __future__ import annotations

import time
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
from asr_crawler.main import run_pipeline
from asr_crawler.state import ProcessingState


def _engines(*names: str) -> TranscriptionConfig:
    base = TranscriptionConfig(output_suffix="", diarize=False)
    base.engines = [TranscriptionConfig(name=n, diarize=False) for n in names]
    return base


def _config(tmp_path: Path, **overrides) -> Config:
    cfg = Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=False,
        state=StateConfig(),
        formatter=FormatterConfig(format="txt"),
        transcription=TranscriptionConfig(output_suffix="", diarize=False),
        postprocessing=OllamaStepConfig(llm_enabled=False, regex_enabled=False),
        file_summarization=OllamaStepConfig(llm_enabled=False),
        dir_summarization=DirSummarizationConfig(llm_enabled=False),
        schedule=ScheduleConfig(),
        logging=LoggingConfig(),
    )
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def _run(cfg: Config, transcripts: dict[str, str]) -> list[str]:
    """One pipeline run with per-filename transcripts; returns the files the
    transcriber was actually called for."""
    calls: list[str] = []

    def fake(self, path: Path) -> str:
        calls.append(path.name)
        return transcripts[path.name]

    with patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe", fake):
        run_pipeline(cfg)
    return calls


def _dir_result(tmp_path: Path, label: str = "") -> str:
    return (tmp_path / f"{tmp_path.name}{label}.txt").read_text(encoding="utf-8")


class TestIncrementalRebuild:
    def test_new_file_rebuilds_full_dir_result(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        (tmp_path / "b.mp3").write_bytes(b"\x00")
        _run(_config(tmp_path), {"a.mp3": "text a", "b.mp3": "text b"})

        (tmp_path / "c.mp3").write_bytes(b"\x00")
        assert _run(_config(tmp_path), {"c.mp3": "text c"}) == ["c.mp3"]

        content = _dir_result(tmp_path)
        for name, text in (("a.mp3", "text a"), ("b.mp3", "text b"), ("c.mp3", "text c")):
            assert name in content  # filename header
            assert text in content  # transcript block

    def test_rebuilt_result_matches_a_from_scratch_full_run(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        (tmp_path / "b.mp3").write_bytes(b"\x00")
        _run(_config(tmp_path), {"a.mp3": "text a", "b.mp3": "text b"})
        (tmp_path / "c.mp3").write_bytes(b"\x00")
        _run(_config(tmp_path), {"c.mp3": "text c"})
        incremental = _dir_result(tmp_path)

        scratch = tmp_path / "scratch"  # created after the runs above — never scanned by them
        scratch.mkdir()
        for name in ("a.mp3", "b.mp3", "c.mp3"):
            (scratch / name).write_bytes(b"\x00")
        _run(_config(scratch), {"a.mp3": "text a", "b.mp3": "text b", "c.mp3": "text c"})

        assert incremental == _dir_result(scratch)

    def test_capped_runs_accumulate_into_complete_dir_result(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        (tmp_path / "b.mp3").write_bytes(b"\x00")
        cfg = _config(tmp_path, max_files_per_run=1)
        _run(cfg, {"a.mp3": "text a", "b.mp3": "text b"})
        _run(cfg, {"a.mp3": "text a", "b.mp3": "text b"})

        content = _dir_result(tmp_path)
        assert "text a" in content
        assert "text b" in content

    def test_changed_file_reprocessed_same_run_contributes_new_text(self, tmp_path):
        rec = tmp_path / "a.mp3"
        rec.write_bytes(b"\x00")
        _run(_config(tmp_path), {"a.mp3": "old text"})

        time.sleep(0.01)
        rec.write_bytes(b"\x00\x01\x02")  # mtime + size change → requeued
        assert _run(_config(tmp_path), {"a.mp3": "new text"}) == ["a.mp3"]

        content = _dir_result(tmp_path)
        assert "new text" in content
        assert "old text" not in content


class TestOmissions:
    def test_backfilled_file_without_stored_text_is_omitted_with_warning(self, tmp_path, caplog):
        # a pre-index catalog entry: a.mp3 already has its result on disk and no
        # index row → back-filled "done" by discovery, with no stored text to
        # rebuild the directory result from.
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        (tmp_path / "a.txt").write_text("old result", encoding="utf-8")
        (tmp_path / "b.mp3").write_bytes(b"\x00")

        with caplog.at_level("WARNING"):
            assert _run(_config(tmp_path), {"b.mp3": "text b"}) == ["b.mp3"]

        content = _dir_result(tmp_path)
        assert "text b" in content
        assert "a.mp3" not in content  # nothing to contribute — omitted, not failed
        assert "omits 1 file(s) with no stored text: a.mp3" in caplog.text
        with ProcessingState.open(tmp_path / "db" / "state.db") as idx:
            assert idx.get_errors() == []

    def test_skip_marker_and_max_age_files_are_not_censused(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        (tmp_path / "old_skip.mp3").write_bytes(b"\x00")
        cfg = _config(tmp_path, skip_marker="_skip")
        _run(cfg, {"a.mp3": "text a"})

        content = _dir_result(tmp_path)
        assert "text a" in content
        assert "old_skip.mp3" not in content


class TestMultiEngine:
    def test_each_engine_rebuilds_from_its_own_texts(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        cfg = _config(tmp_path, transcription=_engines("e1", "e2"))
        _run(cfg, {"a.mp3": "text a"})

        (tmp_path / "b.mp3").write_bytes(b"\x00")
        calls = _run(cfg, {"b.mp3": "text b"})
        assert sorted(calls) == ["b.mp3", "b.mp3"]  # one call per engine, a resumed from index

        for name in ("e1", "e2"):
            content = _dir_result(tmp_path, f"_{name}")
            assert "text a" in content  # from that engine's stored text
            assert "text b" in content  # from this run

    def test_engine_added_later_gets_only_the_files_it_transcribed(self, tmp_path, caplog):
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        _run(_config(tmp_path), {"a.mp3": "text a"})  # implicit engine

        (tmp_path / "b.mp3").write_bytes(b"\x00")
        cfg = _config(tmp_path, transcription=_engines("e2"))
        with caplog.at_level("WARNING"):
            assert _run(cfg, {"b.mp3": "text b"}) == ["b.mp3"]

        content = _dir_result(tmp_path, "_e2")
        assert "text b" in content
        assert "a.mp3" not in content  # never transcribed by e2 — omitted
        assert "omits 1 file(s) with no stored text: a.mp3" in caplog.text


class TestConcatSourceFallback:
    def test_per_file_fallback_when_stored_file_has_no_fixed_text(self, tmp_path):
        # run 1 with postprocessing off → a has only raw asr text stored
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        _run(_config(tmp_path), {"a.mp3": "raw a"})

        # run 2 with postprocessing on → b gets fixed text; a is done and
        # contributes its stored raw transcript (per-file fallback)
        (tmp_path / "b.mp3").write_bytes(b"\x00")
        cfg = _config(tmp_path)
        cfg.postprocessing = OllamaStepConfig(llm_enabled=True, regex_enabled=False)
        with patch(
            "asr_crawler.pipeline.postprocessor.PostProcessor.process",
            lambda self, t, source_path=None: f"fixed {t}",
        ):
            _run(cfg, {"b.mp3": "raw b"})

        content = _dir_result(tmp_path)
        assert "raw a" in content  # stored asr fallback
        assert "fixed raw b" in content  # fresh fixed text


class TestRefreshUnchanged:
    def test_refresh_still_rebuilds_the_full_dir_result(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        _run(_config(tmp_path), {"a.mp3": "text a"})
        before = _dir_result(tmp_path)

        with patch(
            "asr_crawler.pipeline.transcriber.Transcriber.transcribe",
            lambda self, p: (_ for _ in ()).throw(AssertionError("no transcribe")),
        ):
            run_pipeline(_config(tmp_path), refresh=True)

        assert _dir_result(tmp_path) == before
