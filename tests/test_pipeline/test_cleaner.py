"""Tests for pipeline Cleaner."""
from pathlib import Path

import pytest

from whispercrawl.config import CleanupConfig
from whispercrawl.pipeline.cleaner import Cleaner

DEFAULT_SUFFIXES = ["", "_fix", "_sum"]


def _make_outputs(audio: Path, suffixes=DEFAULT_SUFFIXES, ext=".txt") -> list[Path]:
    files = [audio.with_name(audio.stem + s + ext) for s in suffixes]
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

        Cleaner(CleanupConfig(targets=[""], on="success")).clean(audio, success=True)

        assert not txt.exists()
        assert fix.exists()

    def test_missing_target_files_are_silently_skipped(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()

        Cleaner(CleanupConfig(on="always")).clean(audio, success=True)

    def test_html_format_removes_html_files(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        outputs = _make_outputs(audio, ext=".html")

        Cleaner(CleanupConfig(on="success"), output_format="html").clean(audio, success=True)

        assert not any(f.exists() for f in outputs)

    def test_html_format_does_not_remove_txt_files(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        txt = audio.with_name("call.txt")
        txt.write_text("x")

        Cleaner(CleanupConfig(targets=[""], on="success"), output_format="html").clean(audio, success=True)

        assert txt.exists()
