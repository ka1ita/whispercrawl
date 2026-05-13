"""Tests for pipeline Cleaner."""
from pathlib import Path

import pytest

from whispercrawl.config import CleanupConfig
from whispercrawl.pipeline.cleaner import Cleaner

DEFAULT_SUFFIXES = [".txt", "_fix.txt", "_sum.txt"]


def _make_outputs(audio: Path, suffixes=DEFAULT_SUFFIXES) -> list[Path]:
    files = [audio.with_name(audio.stem + s) for s in suffixes]
    for f in files:
        f.write_text("content")
    return files


class TestCleanerOnSuccess:
    def test_removes_all_targets_on_success(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        outputs = _make_outputs(audio)

        Cleaner(CleanupConfig(on="success")).clean(audio, success=True)

        assert not any(f.exists() for f in outputs)

    def test_keeps_files_on_failure(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        outputs = _make_outputs(audio)

        Cleaner(CleanupConfig(on="success")).clean(audio, success=False)

        assert all(f.exists() for f in outputs)


class TestCleanerOnAlways:
    def test_removes_on_success(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        outputs = _make_outputs(audio)

        Cleaner(CleanupConfig(on="always")).clean(audio, success=True)

        assert not any(f.exists() for f in outputs)

    def test_removes_on_failure(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        outputs = _make_outputs(audio)

        Cleaner(CleanupConfig(on="always")).clean(audio, success=False)

        assert not any(f.exists() for f in outputs)


class TestCleanerTargets:
    def test_only_removes_listed_suffixes(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        txt = audio.with_name("call.txt")
        fix = audio.with_name("call_fix.txt")
        txt.write_text("t")
        fix.write_text("f")

        Cleaner(CleanupConfig(targets=[".txt"], on="success")).clean(audio, success=True)

        assert not txt.exists()
        assert fix.exists()

    def test_missing_target_files_are_silently_skipped(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()

        Cleaner(CleanupConfig(on="always")).clean(audio, success=True)
