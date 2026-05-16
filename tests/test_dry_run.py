"""Integration test for --once --dry-run mode."""
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from whispercrawl.config import (
    CleanupConfig, Config, LoggingConfig, OllamaStepConfig,
    ScheduleConfig, TranscriptionConfig,
)
from whispercrawl.main import run_pipeline


def _config(tmp_path: Path) -> Config:
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=True,
        transcription=TranscriptionConfig(output_suffix=""),
        postprocessing=OllamaStepConfig(llm_enabled=True),
        file_summarization=OllamaStepConfig(llm_enabled=True),
        dir_summarization=OllamaStepConfig(llm_enabled=True),
        schedule=ScheduleConfig(),
        cleanup=CleanupConfig(),
        logging=LoggingConfig(),
    )


class TestDryRun:
    def test_logs_files_that_would_be_processed(self, tmp_path, caplog):
        (tmp_path / "a.mp3").write_bytes(b"\x00")
        (tmp_path / "b.mp3").write_bytes(b"\x00")

        with caplog.at_level(logging.INFO):
            run_pipeline(_config(tmp_path), dry_run=True)

        logged = caplog.text
        assert "a.mp3" in logged
        assert "b.mp3" in logged

    def test_makes_no_http_calls(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"\x00")

        with patch("whispercrawl.pipeline.transcriber.httpx.post") as mock_post:
            run_pipeline(_config(tmp_path), dry_run=True)

        mock_post.assert_not_called()

    def test_writes_no_output_files(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"\x00")

        run_pipeline(_config(tmp_path), dry_run=True)

        output_files = [f for f in tmp_path.iterdir() if f.suffix != ".mp3"]
        assert output_files == []

    def test_empty_directory_logs_no_files_message(self, tmp_path, caplog):
        with caplog.at_level(logging.INFO):
            run_pipeline(_config(tmp_path), dry_run=True)

        assert "No files to process" in caplog.text

    def test_skips_already_transcribed_when_rescan_false(self, tmp_path, caplog):
        audio = tmp_path / "a.mp3"
        audio.write_bytes(b"\x00")
        (tmp_path / "a.txt").write_text("existing", encoding="utf-8")

        cfg = _config(tmp_path)
        cfg.rescan = False

        with caplog.at_level(logging.INFO):
            run_pipeline(cfg, dry_run=True)

        assert "No files to process" in caplog.text
