"""Tests for rescan: true cleaning stale cross-format output files (EPIC-029)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from whispercrawl.config import (
    CleanupConfig,
    Config,
    FormatterConfig,
    LoggingConfig,
    OllamaStepConfig,
    ScheduleConfig,
    TranscriptionConfig,
)
from whispercrawl.main import run_pipeline
from whispercrawl.pipeline.cleaner import Cleaner


def _config(tmp_path: Path, fmt: str, rescan: bool = True) -> Config:
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=rescan,
        formatter=FormatterConfig(format=fmt),
        transcription=TranscriptionConfig(output_suffix="", error_suffix="_err"),
        postprocessing=OllamaStepConfig(llm_enabled=False, regex_enabled=False),
        file_summarization=OllamaStepConfig(llm_enabled=False),
        dir_summarization=OllamaStepConfig(llm_enabled=False),
        schedule=ScheduleConfig(),
        cleanup=CleanupConfig(targets=["", "_fix", "_sum"]),
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

        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", return_value="transcript"):
            run_pipeline(_config(tmp_path, current_fmt))

        assert not stale.exists()

    def test_stale_sum_deleted(self, tmp_path, stale_ext, current_fmt):
        (tmp_path / "rec.mp3").touch()
        stale = tmp_path / f"rec_sum{stale_ext}"
        stale.write_text("old summary")

        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", return_value="transcript"):
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

        with patch("whispercrawl.pipeline.transcriber.Transcriber.transcribe", return_value="transcript"):
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
    def test_err_suffix_not_in_labels_so_err_file_untouched(self, tmp_path):
        err = tmp_path / "rec_err.txt"
        err.write_text("error")

        cleaner = Cleaner(CleanupConfig(targets=["", "_sum"]), "md")
        cleaner.clean_other_formats(tmp_path / "rec.mp3", ["", "_sum"])

        assert err.exists()

    def test_json_target_filtered_at_call_site(self, tmp_path):
        diarize = tmp_path / "rec_diarize.json"
        diarize.write_text("{}")

        cleaner = Cleaner(CleanupConfig(targets=["", "_diarize.json"]), "md")
        # Simulate what run_pipeline does: filter out .json entries before passing
        labels = [s for s in ["", "_diarize.json"] if not s.endswith(".json")]
        cleaner.clean_other_formats(tmp_path / "rec.mp3", labels)

        assert diarize.exists()

    def test_current_ext_files_not_deleted(self, tmp_path):
        current = tmp_path / "rec.md"
        current.write_text("current output")

        cleaner = Cleaner(CleanupConfig(targets=[""]), "md")
        cleaner.clean_other_formats(tmp_path / "rec.mp3", [""])

        assert current.exists()

    def test_no_stale_files_is_no_op(self, tmp_path):
        cleaner = Cleaner(CleanupConfig(targets=["", "_sum"]), "md")
        cleaner.clean_other_formats(tmp_path / "rec.mp3", ["", "_sum"])
        # Should not raise; nothing to delete

    def test_dry_run_does_not_delete(self, tmp_path):
        stale = tmp_path / "rec.txt"
        stale.write_text("stale")

        cleaner = Cleaner(CleanupConfig(targets=[""]), "md")
        cleaner.clean_other_formats(tmp_path / "rec.mp3", [""], dry_run=True)

        assert stale.exists()
