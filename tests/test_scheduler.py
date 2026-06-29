"""Tests for scheduler immediate-first-run behaviour."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from whispercrawl.config import (
    CleanupConfig, Config, LoggingConfig,
    OllamaStepConfig, ScheduleConfig, TranscriptionConfig,
)
from whispercrawl.scheduler import start_scheduler


def _config(tmp_path: Path, schedule: ScheduleConfig) -> Config:
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        rescan=True,
        transcription=TranscriptionConfig(output_suffix=""),
        postprocessing=OllamaStepConfig(llm_enabled=False),
        file_summarization=OllamaStepConfig(llm_enabled=False),
        dir_summarization=OllamaStepConfig(llm_enabled=False),
        schedule=schedule,
        cleanup=CleanupConfig(),
        logging=LoggingConfig(),
    )


class TestImmediateFirstRun:
    def _run(self, cfg: Config):
        call_order: list[str] = []

        def fake_run_pipeline(c, dry_run=False):
            call_order.append("run_pipeline")

        mock_scheduler = MagicMock()

        def fake_start():
            call_order.append("scheduler_start")

        mock_scheduler.start.side_effect = fake_start

        with (
            patch("whispercrawl.scheduler.run_pipeline", side_effect=fake_run_pipeline),
            patch("whispercrawl.scheduler.BlockingScheduler", return_value=mock_scheduler),
            patch("whispercrawl.scheduler.signal.signal"),
        ):
            start_scheduler(cfg)

        return call_order, mock_scheduler

    def test_interval_runs_pipeline_before_scheduler_starts(self, tmp_path):
        cfg = _config(tmp_path, ScheduleConfig(interval="30m"))
        order, _ = self._run(cfg)
        assert order == ["run_pipeline", "scheduler_start"]

    def test_cron_runs_pipeline_before_scheduler_starts(self, tmp_path):
        cfg = _config(tmp_path, ScheduleConfig(cron="0 * * * *"))
        order, _ = self._run(cfg)
        assert order == ["run_pipeline", "scheduler_start"]

    def test_interval_job_still_registered(self, tmp_path):
        cfg = _config(tmp_path, ScheduleConfig(interval="30m"))
        _, mock_scheduler = self._run(cfg)
        mock_scheduler.add_job.assert_called_once()
        assert mock_scheduler.add_job.call_args[0][1] == "interval"

    def test_cron_job_still_registered(self, tmp_path):
        cfg = _config(tmp_path, ScheduleConfig(cron="0 * * * *"))
        _, mock_scheduler = self._run(cfg)
        mock_scheduler.add_job.assert_called_once()
        assert mock_scheduler.add_job.call_args[0][1] == "cron"
