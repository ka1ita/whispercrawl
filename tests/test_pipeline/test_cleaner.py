"""Tests for pipeline Cleaner — removes only the consolidated result (EPIC-052)."""
from pathlib import Path

from whispercrawl.config import CleanupConfig
from whispercrawl.pipeline.cleaner import Cleaner


def _result(audio: Path, ext=".txt", label="") -> Path:
    p = audio.with_name(audio.stem + label + ext)
    p.write_text("content")
    return p


class TestCleanerOnSuccess:
    def test_removes_result_on_success(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        result = _result(audio)

        Cleaner(CleanupConfig(on="success")).clean(audio, success=True)

        assert not result.exists()

    def test_keeps_result_on_failure(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        result = _result(audio)

        Cleaner(CleanupConfig(on="success")).clean(audio, success=False)

        assert result.exists()


class TestCleanerOnAlways:
    def test_removes_on_failure(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        result = _result(audio)

        Cleaner(CleanupConfig(on="always")).clean(audio, success=False)

        assert not result.exists()


class TestCleanerScope:
    def test_leaves_pre047_sidecars_alone(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        result = _result(audio)
        fix = audio.with_name("call_fix.txt")
        err = audio.with_name("call_err.txt")
        fix.write_text("f")
        err.write_text("e")

        Cleaner(CleanupConfig(on="success")).clean(audio, success=True)

        assert not result.exists()
        assert fix.exists()
        assert err.exists()

    def test_missing_result_is_silently_skipped(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        Cleaner(CleanupConfig(on="always")).clean(audio, success=True)

    def test_html_format_removes_only_html_result(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        html = _result(audio, ext=".html")
        txt = _result(audio, ext=".txt")

        Cleaner(CleanupConfig(on="success"), output_format="html").clean(audio, success=True)

        assert not html.exists()
        assert txt.exists()

    def test_removes_result_per_engine_label(self, tmp_path):
        audio = tmp_path / "call.mp3"
        audio.touch()
        a = _result(audio, label="_a")
        b = _result(audio, label="_b")

        Cleaner(CleanupConfig(on="success"), engine_labels=["_a", "_b"]).clean(audio, success=True)

        assert not a.exists()
        assert not b.exists()
