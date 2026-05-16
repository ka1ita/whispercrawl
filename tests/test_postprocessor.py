"""Tests for replace_transcription pipeline behaviour."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from whispercrawl.config import (
    CleanupConfig,
    Config,
    LoggingConfig,
    OllamaStepConfig,
    ScheduleConfig,
    TranscriptionConfig,
)
from whispercrawl.main import run_pipeline


def _config(tmp_path: Path, replace_transcription: bool = False) -> Config:
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=True,
        transcription=TranscriptionConfig(output_suffix="", error_suffix="_err"),
        postprocessing=OllamaStepConfig(
            llm_enabled=True,
            regex_enabled=False,
            output_suffix="_fix",
            error_suffix="_err",
            replace_transcription=replace_transcription,
        ),
        file_summarization=OllamaStepConfig(llm_enabled=False),
        dir_summarization=OllamaStepConfig(llm_enabled=False),
        schedule=ScheduleConfig(),
        cleanup=CleanupConfig(),
        logging=LoggingConfig(),
    )


TRANSCRIPT = "raw transcript"
FIXED = "fixed transcript"


def _make_transcriber(response=TRANSCRIPT):
    inst = MagicMock()
    inst.transcribe.return_value = response
    cls = MagicMock(return_value=inst)
    return cls


def _make_postprocessor(response=FIXED):
    inst = MagicMock()
    inst.process.return_value = response
    cls = MagicMock(return_value=inst)
    return cls


def _make_postprocessor_failing(exc):
    from whispercrawl.pipeline.postprocessor import PostProcessingError
    inst = MagicMock()
    inst.process.side_effect = PostProcessingError(exc)
    cls = MagicMock(return_value=inst)
    return cls


def _svc_logger_patch():
    svc_log = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=svc_log)
    ctx.__exit__ = MagicMock(return_value=False)
    cls = MagicMock(return_value=ctx)
    return cls


def _patches(transcriber_cls, postprocessor_cls):
    return [
        patch("whispercrawl.pipeline.transcriber.Transcriber", transcriber_cls),
        patch("whispercrawl.pipeline.postprocessor.PostProcessor", postprocessor_cls),
        patch("whispercrawl.utils.service_logger.ServiceLogger", _svc_logger_patch()),
    ]


class TestReplaceTranscriptionFalse:
    def test_both_files_written(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        cfg = _config(tmp_path, replace_transcription=False)

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber", _make_transcriber()),
            patch("whispercrawl.pipeline.postprocessor.PostProcessor", _make_postprocessor()),
            patch("whispercrawl.utils.service_logger.ServiceLogger", _svc_logger_patch()),
        ):
            run_pipeline(cfg)

        assert (tmp_path / "a.txt").read_text(encoding="utf-8") == TRANSCRIPT
        assert (tmp_path / "a_fix.txt").read_text(encoding="utf-8") == FIXED

    def test_no_replace_on_postprocess_failure(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        cfg = _config(tmp_path, replace_transcription=False)

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber", _make_transcriber()),
            patch("whispercrawl.pipeline.postprocessor.PostProcessor", _make_postprocessor_failing("boom")),
            patch("whispercrawl.utils.service_logger.ServiceLogger", _svc_logger_patch()),
        ):
            run_pipeline(cfg)

        assert (tmp_path / "a.txt").read_text(encoding="utf-8") == TRANSCRIPT
        assert not (tmp_path / "a_fix.txt").exists()
        assert (tmp_path / "a_err.txt").exists()


class TestReplaceTranscriptionTrue:
    def test_fix_replaces_transcript(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        cfg = _config(tmp_path, replace_transcription=True)

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber", _make_transcriber()),
            patch("whispercrawl.pipeline.postprocessor.PostProcessor", _make_postprocessor()),
            patch("whispercrawl.utils.service_logger.ServiceLogger", _svc_logger_patch()),
        ):
            run_pipeline(cfg)

        assert (tmp_path / "a.txt").read_text(encoding="utf-8") == FIXED
        assert not (tmp_path / "a_fix.txt").exists()

    def test_transcript_unchanged_on_failure(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        cfg = _config(tmp_path, replace_transcription=True)

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber", _make_transcriber()),
            patch("whispercrawl.pipeline.postprocessor.PostProcessor", _make_postprocessor_failing("boom")),
            patch("whispercrawl.utils.service_logger.ServiceLogger", _svc_logger_patch()),
        ):
            run_pipeline(cfg)

        assert (tmp_path / "a.txt").read_text(encoding="utf-8") == TRANSCRIPT
        assert not (tmp_path / "a_fix.txt").exists()
        assert (tmp_path / "a_err.txt").exists()

    def test_log_message_mentions_replace(self, tmp_path, caplog):
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        cfg = _config(tmp_path, replace_transcription=True)

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber", _make_transcriber()),
            patch("whispercrawl.pipeline.postprocessor.PostProcessor", _make_postprocessor()),
            patch("whispercrawl.utils.service_logger.ServiceLogger", _svc_logger_patch()),
            caplog.at_level(logging.INFO),
        ):
            run_pipeline(cfg)

        assert "Replaced transcript" in caplog.text
