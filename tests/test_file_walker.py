"""Tests for file_walker module."""
from pathlib import Path

import pytest

from whispercrawl.file_walker import detect_language, iter_media_files

EXTENSIONS = [".mp3", ".wav", ".mp4"]


class TestDetectLanguage:
    def test_detects_ru(self):
        assert detect_language("meeting_ru", "auto") == "ru"

    def test_detects_en(self):
        assert detect_language("interview_en", "auto") == "en"

    def test_detects_auto(self):
        assert detect_language("call_auto", "en") == "auto"

    def test_falls_back_to_default(self):
        assert detect_language("call", "ru") == "ru"

    def test_case_insensitive(self):
        assert detect_language("meeting_RU", "auto") == "ru"


class TestIterMediaFiles:
    def test_skips_already_transcribed(self, media_dir: Path):
        # call.txt exists → call.mp4 should be skipped
        files = list(iter_media_files(media_dir, EXTENSIONS, ".txt", rescan=False))
        names = [f.name for f in files]
        assert "call.mp4" not in names
        assert "meeting_ru.mp3" in names

    def test_rescan_includes_all(self, media_dir: Path):
        files = list(iter_media_files(media_dir, EXTENSIONS, ".txt", rescan=True))
        names = [f.name for f in files]
        assert "call.mp4" in names
        assert "meeting_ru.mp3" in names

    def test_ignores_non_media_files(self, media_dir: Path):
        files = list(iter_media_files(media_dir, EXTENSIONS, ".txt", rescan=True))
        assert all(f.suffix in EXTENSIONS for f in files)
