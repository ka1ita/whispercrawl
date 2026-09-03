"""Tests for rescan: true cleaning the stale cross-format consolidated result (EPIC-029)."""
from __future__ import annotations

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
    TranscriptionConfig,
)
from asr_crawler.main import run_pipeline
from asr_crawler.pipeline.cleaner import Cleaner


def _config(tmp_path: Path, fmt: str, rescan: bool = True) -> Config:
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=rescan,
        formatter=FormatterConfig(format=fmt),
        transcription=TranscriptionConfig(output_suffix=""),
        postprocessing=OllamaStepConfig(llm_enabled=False, regex_enabled=False),
        file_summarization=OllamaStepConfig(llm_enabled=False),
        dir_summarization=DirSummarizationConfig(llm_enabled=False),
        schedule=ScheduleConfig(),
        logging=LoggingConfig(),
    )


@pytest.mark.parametrize("stale_ext,current_fmt", [
    (".txt", "md"),
    (".txt", "html"),
    (".md",  "html"),
    (".md",  "txt"),
    (".html", "txt"),
    (".html", "md"),
])
class TestRescanCleansOtherFormats:
    def test_stale_transcript_deleted(self, tmp_path, stale_ext, current_fmt):
        (tmp_path / "rec.mp3").touch()
        stale = tmp_path / f"rec{stale_ext}"
        stale.write_text("old output")

        with patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe", return_value="transcript"):
            run_pipeline(_config(tmp_path, current_fmt))

        assert not stale.exists()


class TestRescanFalseDoesNotClean:
    @pytest.mark.parametrize("stale_ext,current_fmt", [
        (".txt", "md"),
        (".md", "html"),
        (".html", "txt"),
    ])
    def test_stale_output_untouched_when_rescan_false(self, tmp_path, stale_ext, current_fmt):
        (tmp_path / "rec.mp3").touch()
        stale = tmp_path / f"rec{stale_ext}"
        stale.write_text("old output")

        with patch("asr_crawler.pipeline.transcriber.Transcriber.transcribe", return_value="transcript"):
            run_pipeline(_config(tmp_path, current_fmt, rescan=False))

        assert stale.exists()


class TestDryRunLogsButDoesNotDelete:
    def test_dry_run_leaves_stale_file(self, tmp_path):
        (tmp_path / "rec.mp3").touch()
        stale = tmp_path / "rec.txt"
        stale.write_text("old output")

        run_pipeline(_config(tmp_path, "md"), dry_run=True)

        assert stale.exists()

    def test_dry_run_rescan_false_leaves_stale_file(self, tmp_path):
        (tmp_path / "rec.mp3").touch()
        stale = tmp_path / "rec.txt"
        stale.write_text("old output")

        run_pipeline(_config(tmp_path, "md", rescan=False), dry_run=True)

        assert stale.exists()


class TestCleanOtherFormatsUnit:
    def test_err_file_untouched(self, tmp_path):
        err = tmp_path / "rec_err.txt"
        err.write_text("error")

        Cleaner("md").clean_other_formats(tmp_path / "rec.mp3")

        assert err.exists()

    def test_pre047_sidecar_untouched(self, tmp_path):
        legacy = tmp_path / "rec_sum.txt"
        legacy.write_text("old summary")

        Cleaner("md").clean_other_formats(tmp_path / "rec.mp3")

        assert legacy.exists()

    def test_current_ext_files_not_deleted(self, tmp_path):
        current = tmp_path / "rec.md"
        current.write_text("current output")

        Cleaner("md").clean_other_formats(tmp_path / "rec.mp3")

        assert current.exists()

    def test_stale_ext_consolidated_result_deleted(self, tmp_path):
        stale = tmp_path / "rec.txt"
        stale.write_text("stale")

        Cleaner("md").clean_other_formats(tmp_path / "rec.mp3")

        assert not stale.exists()

    def test_no_stale_files_is_no_op(self, tmp_path):
        Cleaner("md").clean_other_formats(tmp_path / "rec.mp3")
        # Should not raise; nothing to delete

    def test_dry_run_does_not_delete(self, tmp_path):
        stale = tmp_path / "rec.txt"
        stale.write_text("stale")

        Cleaner("md").clean_other_formats(tmp_path / "rec.mp3", dry_run=True)

        assert stale.exists()

    def test_per_engine_labels(self, tmp_path):
        stale = tmp_path / "rec_whisperx.txt"
        stale.write_text("stale")

        Cleaner("md", engine_labels=["_whisperx"]).clean_other_formats(
            tmp_path / "rec.mp3"
        )

        assert not stale.exists()
