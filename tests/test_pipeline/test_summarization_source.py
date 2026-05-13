"""Tests for summarization source selection logic."""
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from whispercrawl.config import Config, OllamaStepConfig, TranscriptionConfig
from whispercrawl.main import _pick_summary_input, run_pipeline


# ── _pick_summary_input unit tests ────────────────────────────────────────────

class TestPickSummaryInput:
    def test_postprocessed_returns_fixed_when_available(self):
        result = _pick_summary_input("postprocessed", "raw", "fixed", "file.mp3")
        assert result == "fixed"

    def test_postprocessed_falls_back_to_transcript_when_no_fixed(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = _pick_summary_input("postprocessed", "raw", None, "file.mp3")
        assert result == "raw"
        assert "file.mp3" in caplog.text
        assert "falling back" in caplog.text

    def test_original_returns_transcript_regardless_of_fixed(self):
        result = _pick_summary_input("original", "raw", "fixed", "file.mp3")
        assert result == "raw"

    def test_original_returns_transcript_when_no_fixed(self):
        result = _pick_summary_input("original", "raw", None, "file.mp3")
        assert result == "raw"


# ── run_pipeline integration tests ────────────────────────────────────────────

def _minimal_config(tmp_path: Path, summarize_source: str, post_llm: bool = True) -> Config:
    from whispercrawl.config import (
        CleanupConfig, LoggingConfig, ScheduleConfig,
    )
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=True,
        transcription=TranscriptionConfig(output_suffix=".txt", error_suffix="_err.txt"),
        postprocessing=OllamaStepConfig(
            llm_enabled=post_llm,
            regex_enabled=False,
            output_suffix="_fix.txt",
            error_suffix="_err.txt",
        ),
        file_summarization=OllamaStepConfig(
            llm_enabled=True,
            summarize_source=summarize_source,
            output_suffix="_sum.txt",
            error_suffix="_err.txt",
        ),
        dir_summarization=OllamaStepConfig(llm_enabled=False),
        schedule=ScheduleConfig(),
        cleanup=CleanupConfig(),
        logging=LoggingConfig(),
    )


def _mock_transcriber_cls(transcript: str):
    inst = MagicMock()
    inst.transcribe.return_value = transcript
    cls = MagicMock(return_value=inst)
    return cls, inst


def _mock_postprocessor_cls(fixed: str):
    inst = MagicMock()
    inst.process.return_value = fixed
    cls = MagicMock(return_value=inst)
    return cls, inst


def _mock_summarizer_cls(summary: str = "summary"):
    inst = MagicMock()
    inst.summarize_file.return_value = summary
    cls = MagicMock(return_value=inst)
    return cls, inst


class TestRunPipelineSummarizationSource:
    def test_postprocessed_source_passes_fixed_text_to_summarizer(self, tmp_path):
        audio = tmp_path / "rec.mp3"
        audio.write_bytes(b"\x00")

        config = _minimal_config(tmp_path, "postprocessed")
        tr_cls, tr_inst = _mock_transcriber_cls("original text")
        pp_cls, pp_inst = _mock_postprocessor_cls("fixed text")
        sm_cls, sm_inst = _mock_summarizer_cls()

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber", tr_cls),
            patch("whispercrawl.pipeline.postprocessor.PostProcessor", pp_cls),
            patch("whispercrawl.pipeline.summarizer.Summarizer", sm_cls),
            patch("whispercrawl.utils.service_logger.ServiceLogger") as mock_svc_log_cls,
        ):
            mock_svc_log_cls.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_svc_log_cls.return_value.__exit__ = MagicMock(return_value=False)
            run_pipeline(config)

        sm_inst.summarize_file.assert_called_once()
        text_used = sm_inst.summarize_file.call_args.args[0]
        assert text_used == "fixed text"

    def test_original_source_passes_transcript_to_summarizer(self, tmp_path):
        audio = tmp_path / "rec.mp3"
        audio.write_bytes(b"\x00")

        config = _minimal_config(tmp_path, "original")
        tr_cls, tr_inst = _mock_transcriber_cls("original text")
        pp_cls, pp_inst = _mock_postprocessor_cls("fixed text")
        sm_cls, sm_inst = _mock_summarizer_cls()

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber", tr_cls),
            patch("whispercrawl.pipeline.postprocessor.PostProcessor", pp_cls),
            patch("whispercrawl.pipeline.summarizer.Summarizer", sm_cls),
            patch("whispercrawl.utils.service_logger.ServiceLogger") as mock_svc_log_cls,
        ):
            mock_svc_log_cls.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_svc_log_cls.return_value.__exit__ = MagicMock(return_value=False)
            run_pipeline(config)

        sm_inst.summarize_file.assert_called_once()
        text_used = sm_inst.summarize_file.call_args.args[0]
        assert text_used == "original text"

    def test_postprocessed_source_falls_back_when_no_postprocessor(self, tmp_path, caplog):
        audio = tmp_path / "rec.mp3"
        audio.write_bytes(b"\x00")

        config = _minimal_config(tmp_path, "postprocessed", post_llm=False)
        tr_cls, _ = _mock_transcriber_cls("original text")
        sm_cls, sm_inst = _mock_summarizer_cls()

        with (
            patch("whispercrawl.pipeline.transcriber.Transcriber", tr_cls),
            patch("whispercrawl.pipeline.summarizer.Summarizer", sm_cls),
            patch("whispercrawl.utils.service_logger.ServiceLogger") as mock_svc_log_cls,
            caplog.at_level(logging.WARNING),
        ):
            mock_svc_log_cls.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_svc_log_cls.return_value.__exit__ = MagicMock(return_value=False)
            run_pipeline(config)

        sm_inst.summarize_file.assert_called_once()
        text_used = sm_inst.summarize_file.call_args.args[0]
        assert text_used == "original text"
        assert "falling back" in caplog.text
