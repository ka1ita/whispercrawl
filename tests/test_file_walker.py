"""Tests for file_walker module."""
import os
import time
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
        files = list(iter_media_files(media_dir, EXTENSIONS, "", rescan=False, output_format="txt"))
        names = [f.name for f in files]
        assert "call.mp4" not in names
        assert "meeting_ru.mp3" in names

    def test_rescan_includes_all(self, media_dir: Path):
        files = list(iter_media_files(media_dir, EXTENSIONS, "", rescan=True, output_format="txt"))
        names = [f.name for f in files]
        assert "call.mp4" in names
        assert "meeting_ru.mp3" in names

    def test_ignores_non_media_files(self, media_dir: Path):
        files = list(iter_media_files(media_dir, EXTENSIONS, "", rescan=True, output_format="txt"))
        assert all(f.suffix in EXTENSIONS for f in files)

    def test_skips_already_transcribed_html_format(self, tmp_path: Path):
        (tmp_path / "rec.mp3").touch()
        (tmp_path / "rec.html").touch()
        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=False, output_format="html"))
        assert [f.name for f in files] == []

    def test_skips_already_transcribed_md_format(self, tmp_path: Path):
        (tmp_path / "rec.mp3").touch()
        (tmp_path / "rec.md").touch()
        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=False, output_format="md"))
        assert [f.name for f in files] == []

    @pytest.mark.parametrize("existing_ext,current_format", [
        (".txt", "md"),
        (".txt", "html"),
        (".md",  "txt"),
        (".md",  "html"),
        (".html", "txt"),
        (".html", "md"),
    ])
    def test_skips_when_output_exists_in_different_format(
        self, tmp_path: Path, existing_ext: str, current_format: str
    ):
        (tmp_path / "rec.mp3").touch()
        (tmp_path / f"rec{existing_ext}").touch()
        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=False, output_format=current_format))
        assert [f.name for f in files] == []

    @pytest.mark.parametrize("existing_ext,current_format", [
        (".txt", "md"),
        (".md",  "html"),
        (".html", "txt"),
    ])
    def test_rescan_requeues_despite_cross_format_output(
        self, tmp_path: Path, existing_ext: str, current_format: str
    ):
        (tmp_path / "rec.mp3").touch()
        (tmp_path / f"rec{existing_ext}").touch()
        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=True, output_format=current_format))
        assert [f.name for f in files] == ["rec.mp3"]

    def test_skip_marker_excludes_file(self, tmp_path: Path):
        (tmp_path / "meeting_skip.mp3").touch()
        (tmp_path / "other.mp3").touch()
        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=False, skip_marker="_skip"))
        assert [f.name for f in files] == ["other.mp3"]

    def test_skip_marker_case_insensitive(self, tmp_path: Path):
        (tmp_path / "meeting_SKIP.mp3").touch()
        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=False, skip_marker="_skip"))
        assert files == []

    def test_skip_marker_mid_stem(self, tmp_path: Path):
        (tmp_path / "my_skip_recording.mp3").touch()
        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=False, skip_marker="_skip"))
        assert files == []

    def test_skip_marker_empty_disables_feature(self, tmp_path: Path):
        (tmp_path / "meeting_skip.mp3").touch()
        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=False, skip_marker=""))
        assert [f.name for f in files] == ["meeting_skip.mp3"]

    def test_skip_marker_no_output_still_skipped(self, tmp_path: Path):
        # marker check runs before output-existence check; no output file needed
        (tmp_path / "rec_skip.mp3").touch()
        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=False, skip_marker="_skip"))
        assert files == []

    def test_yields_newest_first(self, tmp_path: Path):
        old = tmp_path / "old.mp3"
        mid = tmp_path / "mid.mp3"
        new = tmp_path / "new.mp3"
        now = time.time()
        old.touch()
        os.utime(old, (now - 300, now - 300))
        mid.touch()
        os.utime(mid, (now - 200, now - 200))
        new.touch()
        os.utime(new, (now - 100, now - 100))

        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=True))
        assert [f.name for f in files] == ["new.mp3", "mid.mp3", "old.mp3"]

    def test_max_age_days_excludes_older_files(self, tmp_path: Path):
        old = tmp_path / "old.mp3"
        recent = tmp_path / "recent.mp3"
        now = time.time()
        old.touch()
        os.utime(old, (now - 10 * 86400, now - 10 * 86400))
        recent.touch()
        os.utime(recent, (now - 86400, now - 86400))

        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=True, max_age_days=5))
        assert [f.name for f in files] == ["recent.mp3"]

    def test_max_age_days_none_is_unbounded(self, tmp_path: Path):
        ancient = tmp_path / "ancient.mp3"
        now = time.time()
        ancient.touch()
        os.utime(ancient, (now - 3650 * 86400, now - 3650 * 86400))

        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=True, max_age_days=None))
        assert [f.name for f in files] == ["ancient.mp3"]

    def test_max_age_days_combines_with_skip_marker_and_output_check(self, tmp_path: Path):
        now = time.time()

        marked = tmp_path / "rec_skip.mp3"
        marked.touch()
        os.utime(marked, (now, now))

        old = tmp_path / "old.mp3"
        old.touch()
        os.utime(old, (now - 10 * 86400, now - 10 * 86400))

        already_done = tmp_path / "done.mp3"
        already_done.touch()
        os.utime(already_done, (now, now))
        (tmp_path / "done.txt").touch()

        keep = tmp_path / "keep.mp3"
        keep.touch()
        os.utime(keep, (now, now))

        files = list(iter_media_files(
            tmp_path, EXTENSIONS, "", rescan=False, skip_marker="_skip", max_age_days=5,
        ))
        assert [f.name for f in files] == ["keep.mp3"]
