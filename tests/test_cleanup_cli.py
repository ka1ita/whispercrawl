"""Tests for --cleanup CLI action (run_cleanup)."""
from pathlib import Path

import pytest

from whispercrawl.config import CleanupConfig, Config, ScheduleConfig, TranscriptionConfig, OllamaStepConfig, LoggingConfig
from whispercrawl.main import run_cleanup

EXTENSIONS = [".mp3", ".ogg", ".wav"]


def _config(watch_dir: Path, targets=None) -> Config:
    if targets is None:
        targets = ["", "_fix", "_sum"]
    return Config(
        watch_dir=watch_dir,
        extensions=EXTENSIONS,
        cleanup=CleanupConfig(targets=targets, on="success"),
        logging=LoggingConfig(),
    )


def _touch(path: Path, text: str = "x") -> Path:
    path.write_text(text)
    return path


class TestRunCleanupDeletes:
    def test_removes_output_files(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        txt = _touch(tmp_path / "call.txt")
        fix = _touch(tmp_path / "call_fix.txt")
        summ = _touch(tmp_path / "call_sum.txt")

        run_cleanup(_config(tmp_path))

        assert not txt.exists()
        assert not fix.exists()
        assert not summ.exists()
        assert audio.exists()  # source file untouched

    def test_removes_dir_summary(self, tmp_path):
        audio = tmp_path / "rec.ogg"
        audio.touch()
        dir_sum = _touch(tmp_path / (tmp_path.name + "_sum.txt"))

        run_cleanup(_config(tmp_path))

        assert not dir_sum.exists()

    def test_only_removes_configured_targets(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        txt = _touch(tmp_path / "call.txt")
        fix = _touch(tmp_path / "call_fix.txt")

        run_cleanup(_config(tmp_path, targets=[""]))

        assert not txt.exists()
        assert fix.exists()  # not in targets

    def test_recursive_subdirectory(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        audio = sub / "meeting.mp3"
        audio.touch()
        txt = _touch(sub / "meeting.txt")

        run_cleanup(_config(tmp_path))

        assert not txt.exists()


class TestRunCleanupDryRun:
    def test_dry_run_keeps_files(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        txt = _touch(tmp_path / "call.txt")

        run_cleanup(_config(tmp_path), dry_run=True)

        assert txt.exists()

    def test_dry_run_dir_summary_kept(self, tmp_path):
        audio = tmp_path / "rec.ogg"
        audio.touch()
        dir_sum = _touch(tmp_path / (tmp_path.name + "_sum.txt"))

        run_cleanup(_config(tmp_path), dry_run=True)

        assert dir_sum.exists()


class TestRunCleanupErrFiles:
    def test_removes_err_files(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        err = _touch(tmp_path / "call_err.txt")

        run_cleanup(_config(tmp_path))

        assert not err.exists()

    def test_removes_err_file_without_media_sibling(self, tmp_path):
        # orphan _err.txt with no matching media file should still be removed
        err = _touch(tmp_path / "orphan_err.txt")
        audio = tmp_path / "call.mp3"  # keep at least one media file so rglob has something
        audio.touch()

        run_cleanup(_config(tmp_path))

        assert not err.exists()

    def test_removes_err_files_recursively(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "rec.wav").touch()
        err = _touch(sub / "rec_err.txt")

        run_cleanup(_config(tmp_path))

        assert not err.exists()

    def test_dry_run_keeps_err_files(self, tmp_path):
        (tmp_path / "call.mp3").touch()
        err = _touch(tmp_path / "call_err.txt")

        run_cleanup(_config(tmp_path), dry_run=True)

        assert err.exists()


class TestRunCleanupNoOutputs:
    def test_no_outputs_exits_cleanly(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        # no .txt or other output files — should not raise
        run_cleanup(_config(tmp_path))

    def test_empty_dir_exits_cleanly(self, tmp_path):
        run_cleanup(_config(tmp_path))
