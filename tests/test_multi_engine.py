"""Integration tests for multiple ASR engines (EPIC-048)."""
from __future__ import annotations

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
from whispercrawl.state import ProcessingState


def _config(tmp_path: Path, engine_names, *, fmt="txt", mode="per_file",
            pp=False, filesum=False, dirsum=False, rescan=True) -> Config:
    base = TranscriptionConfig(output_suffix="", error_suffix="_err", diarize=False)
    base.engines = [TranscriptionConfig(name=n, diarize=False) for n in engine_names] if engine_names else []
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=rescan,
        processing_mode=mode,
        state=StateConfig(enabled=True, store_text=True),
        formatter=FormatterConfig(format=fmt),
        transcription=base,
        postprocessing=OllamaStepConfig(llm_enabled=pp, regex_enabled=False),
        file_summarization=OllamaStepConfig(llm_enabled=filesum),
        dir_summarization=DirSummarizationConfig(llm_enabled=dirsum, error_suffix="_err"),
        schedule=ScheduleConfig(),
        cleanup=CleanupConfig(targets=[]),
        logging=LoggingConfig(),
    )


def _by_engine(self, path: Path) -> str:
    return f"{self.config.name or 'def'}::{path.name}"


def _fail_b(self, path: Path) -> str:
    if self.config.name == "b":
        raise TranscriptionError("boom")
    return f"a::{path.name}"


class TestTwoEngines:
    def test_one_result_per_engine_per_file_and_dir(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")
        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", _by_engine):
            run_pipeline(_config(tmp_path, ["wx", "fw"]))

        assert (tmp_path / "rec_wx.txt").read_text(encoding="utf-8") == "wx::rec.mp3"
        assert (tmp_path / "rec_fw.txt").read_text(encoding="utf-8") == "fw::rec.mp3"
        assert (tmp_path / f"{tmp_path.name}_wx.txt").exists()
        assert (tmp_path / f"{tmp_path.name}_fw.txt").exists()
        # no unlabelled result
        assert not (tmp_path / "rec.txt").exists()

    def test_index_stores_text_per_engine(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")
        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", _by_engine):
            run_pipeline(_config(tmp_path, ["wx", "fw"], rescan=False))

        st = (tmp_path / "rec.mp3").stat()
        with ProcessingState.open(tmp_path / "db" / "state.db") as idx:
            assert idx.get_text("rec.mp3", "asr", st.st_mtime, st.st_size, "wx") == "wx::rec.mp3"
            assert idx.get_text("rec.mp3", "asr", st.st_mtime, st.st_size, "fw") == "fw::rec.mp3"

    def test_single_unnamed_engine_output_is_unlabelled(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")
        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", lambda self, p: "plain"):
            run_pipeline(_config(tmp_path, []))
        assert (tmp_path / "rec.txt").read_text(encoding="utf-8") == "plain"


class TestEngineFailureIsolation:
    def test_one_engine_failure_does_not_block_the_other(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")
        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", _fail_b):
            run_pipeline(_config(tmp_path, ["a", "b"], rescan=False))

        assert (tmp_path / "rec_a.txt").exists()
        assert (tmp_path / "rec_b_err.txt").exists()
        assert not (tmp_path / "rec_b.txt").exists()
        with ProcessingState.open(tmp_path / "db" / "state.db") as idx:
            assert idx.lookup("rec.mp3").status == "error"

    def test_next_run_retries_only_the_failed_engine(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")
        cfg = _config(tmp_path, ["a", "b"], rescan=False)
        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", _fail_b):
            run_pipeline(cfg)

        calls: list[str] = []

        def ok(self, path: Path) -> str:
            calls.append(self.config.name)
            return f"{self.config.name}::{path.name}"

        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", ok):
            run_pipeline(cfg)

        assert calls == ["b"]  # engine a resumed from the index
        assert (tmp_path / "rec_b.txt").exists()
        assert not (tmp_path / "rec_b_err.txt").exists()  # cleared on success
        with ProcessingState.open(tmp_path / "db" / "state.db") as idx:
            assert idx.lookup("rec.mp3").status == "done"


class TestRefreshPerEngine:
    def test_refresh_regenerates_each_engine_without_transcribing(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")
        cfg = _config(tmp_path, ["a", "b"], fmt="md", rescan=False)
        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", _by_engine):
            run_pipeline(cfg)

        def boom(self, p):
            raise AssertionError("must not transcribe during --refresh")

        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", boom):
            run_pipeline(cfg, refresh=True)

        assert (tmp_path / "rec_a.md").exists()
        assert (tmp_path / "rec_b.md").exists()

    def test_refresh_skips_engine_without_stored_text(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")
        # only engine "a" ever ran
        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe",
                   lambda self, p: "a text" if self.config.name == "a" else (_ for _ in ()).throw(TranscriptionError("x"))):
            run_pipeline(_config(tmp_path, ["a", "b"], rescan=False))
        (tmp_path / "rec_b_err.txt").unlink(missing_ok=True)

        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe",
                   lambda self, p: (_ for _ in ()).throw(AssertionError("no transcribe"))):
            run_pipeline(_config(tmp_path, ["a", "b"], rescan=False), refresh=True)

        assert (tmp_path / "rec_a.txt").exists()
        assert not (tmp_path / "rec_b.txt").exists()
        assert not (tmp_path / "rec_b_err.txt").exists()


class TestPerStepEqualsPerFile:
    def test_identical_on_disk_output(self, tmp_path):
        outputs = {}
        for mode in ("per_file", "per_step"):
            d = tmp_path / mode
            d.mkdir()
            (d / "a.mp3").write_bytes(b"\x00")
            (d / "b.mp3").write_bytes(b"\x00")
            with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", _by_engine):
                run_pipeline(_config(d, ["x", "y"], mode=mode))
            outputs[mode] = {
                p.name.replace(mode, "<d>"): p.read_text(encoding="utf-8")
                for p in sorted(d.glob("*.txt"))
            }
        assert outputs["per_file"] == outputs["per_step"]


class TestCleanupPerEngine:
    def test_cleanup_removes_every_engine_result(self, tmp_path):
        (tmp_path / "rec.mp3").write_bytes(b"\x00")
        cfg = _config(tmp_path, ["a", "b"])
        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", _by_engine):
            run_pipeline(cfg)
        assert (tmp_path / "rec_a.txt").exists()

        cfg.cleanup = CleanupConfig(targets=[""], on="success")
        run_cleanup(cfg)

        assert not (tmp_path / "rec_a.txt").exists()
        assert not (tmp_path / "rec_b.txt").exists()
        assert not (tmp_path / f"{tmp_path.name}_a.txt").exists()
        assert not (tmp_path / f"{tmp_path.name}_b.txt").exists()
        assert (tmp_path / "rec.mp3").exists()
