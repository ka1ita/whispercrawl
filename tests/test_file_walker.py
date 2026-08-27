"""Tests for file_walker module."""
import os
import time
from pathlib import Path

import pytest

from whispercrawl.file_walker import detect_language, iter_media_files
from whispercrawl.state import ProcessingState

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


class TestIterMediaFilesWithState:
    def _state(self, tmp_path: Path) -> ProcessingState:
        return ProcessingState.open(tmp_path / "state.db")

    def test_indexed_done_file_skipped_without_exists_probes(self, tmp_path: Path, monkeypatch):
        rec = tmp_path / "rec.mp3"
        rec.touch()
        st = self._state(tmp_path)
        stat = rec.stat()
        st.mark("rec.mp3", "done", stat.st_mtime, stat.st_size)

        calls = {"n": 0}
        real_exists = Path.exists

        def counting_exists(self):
            calls["n"] += 1
            return real_exists(self)

        monkeypatch.setattr(Path, "exists", counting_exists)
        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=False, state=st))

        assert files == []
        assert calls["n"] == 0

    def test_indexed_file_with_changed_mtime_is_requeued(self, tmp_path: Path):
        rec = tmp_path / "rec.mp3"
        rec.touch()
        st = self._state(tmp_path)
        st.mark("rec.mp3", "done", 1.0, rec.stat().st_size)  # stale mtime

        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=False, state=st))
        assert [f.name for f in files] == ["rec.mp3"]

    def test_unindexed_file_with_output_is_backfilled_and_skipped(self, tmp_path: Path):
        rec = tmp_path / "rec.mp3"
        rec.touch()
        (tmp_path / "rec.txt").touch()
        st = self._state(tmp_path)

        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=False, state=st))
        assert files == []

        stat = rec.stat()
        assert st.is_current("rec.mp3", stat.st_mtime, stat.st_size)

    def test_unindexed_file_without_output_is_queued(self, tmp_path: Path):
        rec = tmp_path / "rec.mp3"
        rec.touch()
        st = self._state(tmp_path)

        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=False, state=st))
        assert [f.name for f in files] == ["rec.mp3"]
        assert st.lookup("rec.mp3") is None

    def test_rescan_yields_indexed_done_files(self, tmp_path: Path):
        rec = tmp_path / "rec.mp3"
        rec.touch()
        st = self._state(tmp_path)
        stat = rec.stat()
        st.mark("rec.mp3", "done", stat.st_mtime, stat.st_size)

        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=True, state=st))
        assert [f.name for f in files] == ["rec.mp3"]

    def test_state_none_matches_pre_epic_behavior(self, tmp_path: Path):
        (tmp_path / "a.mp3").touch()
        (tmp_path / "b.mp3").touch()
        (tmp_path / "b.txt").touch()

        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=False, state=None))
        assert [f.name for f in files] == ["a.mp3"]

    def test_skip_marker_and_age_apply_before_state(self, tmp_path: Path):
        now = time.time()
        marked = tmp_path / "rec_skip.mp3"
        marked.touch()
        st = self._state(tmp_path)
        # even if the index somehow says "done", the marker check wins and short-circuits
        st.mark("rec_skip.mp3", "done", marked.stat().st_mtime, marked.stat().st_size)

        old = tmp_path / "old.mp3"
        old.touch()
        os.utime(old, (now - 10 * 86400, now - 10 * 86400))

        keep = tmp_path / "keep.mp3"
        keep.touch()

        files = list(iter_media_files(
            tmp_path, EXTENSIONS, "", rescan=False,
            skip_marker="_skip", max_age_days=5, state=st,
        ))
        assert [f.name for f in files] == ["keep.mp3"]

    def test_state_dir_is_not_walked(self, tmp_path: Path):
        (tmp_path / "rec.mp3").touch()
        hidden = tmp_path / ".whispercrawl"
        hidden.mkdir()
        (hidden / "rec.mp3").touch()  # would be a false candidate if traversed

        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=True))
        assert [f.name for f in files] == ["rec.mp3"]
