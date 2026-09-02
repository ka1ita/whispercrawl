"""Integration tests for `--refresh` — reprocess from stored transcript text (EPIC-046)."""

from __future__ import annotations

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


def _config(tmp_path: Path, *, fmt: str = "txt") -> Config:
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=False,
        state=StateConfig(),
        formatter=FormatterConfig(format=fmt),
        transcription=TranscriptionConfig(output_suffix=""),
        postprocessing=OllamaStepConfig(llm_enabled=False, regex_enabled=True),
        file_summarization=OllamaStepConfig(llm_enabled=False),
        dir_summarization=DirSummarizationConfig(llm_enabled=False),
        schedule=ScheduleConfig(),
        cleanup=CleanupConfig(),
        logging=LoggingConfig(),
    )


def _normal_run(cfg: Config, transcript: str = "[SPEAKER_00]: hello world") -> list[str]:
    calls: list[str] = []

    def fake_transcribe(self, path: Path) -> str:
        calls.append(path.name)
        return transcript

    with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", fake_transcribe):
        run_pipeline(cfg)
    return calls


def test_refresh_does_not_call_transcriber(tmp_path: Path):
    (tmp_path / "rec.mp3").write_bytes(b"\x00")
    assert _normal_run(_config(tmp_path)) == ["rec.mp3"]

    refresh_calls: list[str] = []

    def boom(self, path: Path) -> str:
        refresh_calls.append(path.name)
        raise AssertionError("transcriber must not be called during --refresh")

    with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", boom):
        run_pipeline(_config(tmp_path), refresh=True)

    assert refresh_calls == []
    assert (tmp_path / "rec.txt").exists()


def test_refresh_regenerates_output_with_new_format(tmp_path: Path):
    (tmp_path / "rec.mp3").write_bytes(b"\x00")
    _normal_run(_config(tmp_path, fmt="txt"), transcript="[SPEAKER_00]: hi")
    assert (tmp_path / "rec.txt").exists()

    with patch(
        "whispercrawl.pipeline.transcriber.Transcriber.transcribe",
        lambda self, p: (_ for _ in ()).throw(AssertionError("no transcribe")),
    ):
        run_pipeline(_config(tmp_path, fmt="md"), refresh=True)

    assert (tmp_path / "rec.md").exists()
    assert not (tmp_path / "rec.txt").exists()
    assert "**[SPEAKER_00]:**" in (tmp_path / "rec.md").read_text(encoding="utf-8")


def test_refresh_skips_file_without_stored_text(tmp_path: Path):
    (tmp_path / "rec.mp3").write_bytes(b"\x00")  # never transcribed

    with patch(
        "whispercrawl.pipeline.transcriber.Transcriber.transcribe",
        lambda self, p: (_ for _ in ()).throw(AssertionError("no transcribe")),
    ):
        run_pipeline(_config(tmp_path), refresh=True)

    assert not (tmp_path / "rec.txt").exists()
    assert not (tmp_path / "rec_err.txt").exists()


def test_normal_run_after_refresh_skips_the_file(tmp_path: Path):
    (tmp_path / "rec.mp3").write_bytes(b"\x00")
    _normal_run(_config(tmp_path))

    with patch(
        "whispercrawl.pipeline.transcriber.Transcriber.transcribe",
        lambda self, p: (_ for _ in ()).throw(AssertionError("no transcribe")),
    ):
        run_pipeline(_config(tmp_path), refresh=True)

    later_calls: list[str] = []

    def fake(self, path: Path) -> str:
        later_calls.append(path.name)
        return "x"

    with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", fake):
        run_pipeline(_config(tmp_path))

    assert later_calls == []


def test_refresh_with_no_stored_text_skips_file(tmp_path: Path):
    """The index is always on; a file with no stored transcript is simply skipped."""
    (tmp_path / "rec.mp3").write_bytes(b"\x00")

    with patch(
        "whispercrawl.pipeline.transcriber.Transcriber.transcribe",
        lambda self, p: (_ for _ in ()).throw(AssertionError("no transcribe")),
    ):
        run_pipeline(_config(tmp_path), refresh=True)

    assert not (tmp_path / "rec.txt").exists()


def test_normal_run_populates_text_columns(tmp_path: Path):
    from whispercrawl.state import ProcessingState

    rec = tmp_path / "rec.mp3"
    rec.write_bytes(b"\x00")
    cfg = _config(tmp_path)
    cfg.postprocessing = OllamaStepConfig(llm_enabled=True, regex_enabled=False, output_suffix="_fix")
    with (
        patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", lambda self, p: "raw asr"),
        patch("whispercrawl.pipeline.postprocessor.PostProcessor.process", lambda self, t, source_path=None: "fixed asr"),
    ):
        run_pipeline(cfg)

    st = rec.stat()
    with ProcessingState.open(tmp_path / "db" / "state.db") as idx:
        assert idx.get_text("rec.mp3", "asr", st.st_mtime, st.st_size) == "raw asr"
        assert idx.get_text("rec.mp3", "fixed", st.st_mtime, st.st_size) == "fixed asr"


def test_changed_source_between_runs_is_skipped_by_refresh(tmp_path: Path):
    rec = tmp_path / "rec.mp3"
    rec.write_bytes(b"\x00")
    _normal_run(_config(tmp_path), transcript="[SPEAKER_00]: v1")

    time.sleep(0.01)
    rec.write_bytes(b"\x00\x01\x02")  # mtime + size change

    with patch(
        "whispercrawl.pipeline.transcriber.Transcriber.transcribe",
        lambda self, p: (_ for _ in ()).throw(AssertionError("no transcribe")),
    ):
        run_pipeline(_config(tmp_path, fmt="md"), refresh=True)

    assert not (tmp_path / "rec.md").exists()  # stale stored text not reused


def test_per_step_and_per_file_refresh_produce_identical_output(tmp_path: Path):
    def _build(root: Path, mode: str) -> Config:
        (root / "d").mkdir()
        (root / "d" / "a.mp3").write_bytes(b"\x00")
        (root / "d" / "b.mp3").write_bytes(b"\x00")
        cfg = _config(root, fmt="md")
        cfg.processing_mode = mode
        return cfg

    transcripts = {"a.mp3": "[SPEAKER_00]: alpha", "b.mp3": "[SPEAKER_01]: bravo"}

    def run(mode: str) -> dict[str, str]:
        root = tmp_path / mode
        root.mkdir()
        cfg = _build(root, mode)
        with patch(
            "whispercrawl.pipeline.transcriber.Transcriber.transcribe",
            lambda self, p: transcripts[p.name],
        ):
            run_pipeline(cfg)
        with patch(
            "whispercrawl.pipeline.transcriber.Transcriber.transcribe",
            lambda self, p: (_ for _ in ()).throw(AssertionError("no transcribe")),
        ):
            run_pipeline(cfg, refresh=True)
        return {
            p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(root.rglob("*.md"))
        }

    assert run("per_file") == run("per_step")


def test_refresh_reruns_postprocess_and_summary(tmp_path: Path):
    (tmp_path / "rec.mp3").write_bytes(b"\x00")
    cfg = _config(tmp_path)
    cfg.postprocessing = OllamaStepConfig(llm_enabled=True, regex_enabled=False, output_suffix="_fix")
    cfg.file_summarization = OllamaStepConfig(llm_enabled=True, output_suffix="_sum")

    with (
        patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", lambda self, p: "raw text"),
        patch("whispercrawl.pipeline.postprocessor.PostProcessor.process", lambda self, t, source_path=None: "fixed v1"),
        patch("whispercrawl.pipeline.summarizer.Summarizer.summarize_file", lambda self, t, file="": "sum v1"),
    ):
        run_pipeline(cfg)

    pp_calls: list[str] = []
    sum_calls: list[str] = []

    with (
        patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe",
              lambda self, p: (_ for _ in ()).throw(AssertionError("no transcribe"))),
        patch("whispercrawl.pipeline.postprocessor.PostProcessor.process",
              lambda self, t, source_path=None: pp_calls.append(t) or "fixed v2"),
        patch("whispercrawl.pipeline.summarizer.Summarizer.summarize_file",
              lambda self, t, file="": sum_calls.append(file) or "sum v2"),
    ):
        run_pipeline(cfg, refresh=True)

    assert pp_calls == ["raw text"]          # postprocess re-run from the stored ASR text
    assert sum_calls == ["rec.mp3"]          # summary re-run
    result = (tmp_path / "rec.txt").read_text(encoding="utf-8")
    assert "fixed v2" in result and "sum v2" in result  # composed into the one result file
    assert not (tmp_path / "rec_fix.txt").exists()
    assert not (tmp_path / "rec_sum.txt").exists()
