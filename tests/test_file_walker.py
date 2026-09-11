"""Tests for file_walker module."""
import os
import time
from pathlib import Path

import pytest

from asr_crawler.file_walker import detect_language, directory_media_files, iter_media_files
from asr_crawler.state import ProcessingState

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

    def test_candidate_that_vanishes_before_stat_is_skipped(self, media_dir: Path, monkeypatch):
        """A file removed between the directory scan and its stat() (EPIC-055) is
        skipped rather than crashing the generator with OSError."""
        real_stat = Path.stat

        def flaky_stat(self, *args, **kwargs):
            if self.name == "meeting_ru.mp3":
                raise FileNotFoundError(2, "No such file or directory", str(self))
            return real_stat(self, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", flaky_stat)
        files = list(iter_media_files(media_dir, EXTENSIONS, "", rescan=True, output_format="txt"))
        names = [f.name for f in files]
        assert "meeting_ru.mp3" not in names
        assert "call.mp4" in names

    def test_ignores_non_media_files(self, media_dir: Path):
        files = list(iter_media_files(media_dir, EXTENSIONS, "", rescan=True, output_format="txt"))
        assert all(f.suffix in EXTENSIONS for f in files)

    def test_unsupported_extension_logs_debug_reason(self, media_dir: Path, caplog):
        with caplog.at_level("DEBUG"):
            list(iter_media_files(media_dir, EXTENSIONS, "", rescan=True, output_format="txt"))
        assert "call.txt" in caplog.text
        assert "extension not in configured extensions list" in caplog.text

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
        # age_basis="mtime": the fixture files are freshly created (creation/ctime
        # = now), so only the strict basis keeps this a pure mtime-window test.
        old = tmp_path / "old.mp3"
        recent = tmp_path / "recent.mp3"
        now = time.time()
        old.touch()
        os.utime(old, (now - 10 * 86400, now - 10 * 86400))
        recent.touch()
        os.utime(recent, (now - 86400, now - 86400))

        files = list(iter_media_files(
            tmp_path, EXTENSIONS, "", rescan=True, max_age_days=5, age_basis="mtime",
        ))
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
            age_basis="mtime",
        ))
        assert [f.name for f in files] == ["keep.mp3"]


class TestAgeBasis:
    """EPIC-061: ``max_age_days`` compares a file's arrival timestamp by default —
    the newer of mtime and creation (Windows) / inode-change (Linux) time — so a
    file copied into the tree long after it was last modified is still recent."""

    def test_arrival_ts_returns_newest_of_available_timestamps(self):
        from types import SimpleNamespace

        from asr_crawler.file_walker import _arrival_ts

        # mtime newer than ctime → mtime
        assert _arrival_ts(SimpleNamespace(st_mtime=200.0, st_ctime=100.0)) == 200.0
        # ctime newer — the copied-file case
        assert _arrival_ts(SimpleNamespace(st_mtime=100.0, st_ctime=200.0)) == 200.0
        # birthtime participates when the platform exposes it
        assert _arrival_ts(
            SimpleNamespace(st_mtime=100.0, st_ctime=150.0, st_birthtime=300.0)
        ) == 300.0
        assert _arrival_ts(
            SimpleNamespace(st_mtime=400.0, st_ctime=150.0, st_birthtime=300.0)
        ) == 400.0

    def test_newest_basis_keeps_old_file_copied_in_recently(self, tmp_path: Path):
        # A copy preserves mtime but arrives with a fresh creation (Windows) /
        # inode-change (Linux — os.utime itself bumps ctime) timestamp.
        copied = tmp_path / "copied.mp3"
        copied.touch()
        year_ago = time.time() - 365 * 86400
        os.utime(copied, (year_ago, year_ago))

        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=True, max_age_days=180))
        assert [f.name for f in files] == ["copied.mp3"]

    def test_newest_basis_excludes_file_that_also_arrived_long_ago(
        self, tmp_path: Path, monkeypatch
    ):
        # ctime cannot be set portably, so fake the arrival clock: every file is
        # old by every timestamp.
        import asr_crawler.file_walker as fw

        monkeypatch.setattr(fw, "_arrival_ts", lambda st: time.time() - 365 * 86400)
        (tmp_path / "ancient.mp3").touch()

        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=True, max_age_days=180))
        assert files == []

    def test_mtime_basis_excludes_the_copied_file(self, tmp_path: Path):
        copied = tmp_path / "copied.mp3"
        copied.touch()
        year_ago = time.time() - 365 * 86400
        os.utime(copied, (year_ago, year_ago))

        files = list(iter_media_files(
            tmp_path, EXTENSIONS, "", rescan=True, max_age_days=180, age_basis="mtime",
        ))
        assert files == []

    def test_directory_census_uses_the_same_basis(self, tmp_path: Path):
        copied = tmp_path / "copied.mp3"
        copied.touch()
        year_ago = time.time() - 365 * 86400
        os.utime(copied, (year_ago, year_ago))

        assert [
            p.name for p in directory_media_files(tmp_path, EXTENSIONS, max_age_days=180)
        ] == ["copied.mp3"]
        assert directory_media_files(
            tmp_path, EXTENSIONS, max_age_days=180, age_basis="mtime"
        ) == []


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
            skip_marker="_skip", max_age_days=5, age_basis="mtime", state=st,
        ))
        assert [f.name for f in files] == ["keep.mp3"]

    def test_error_row_with_existing_output_is_still_queued(self, tmp_path: Path):
        # Regression: an earlier step's leftover output (e.g. the transcript)
        # must not silently overwrite a recorded error with "done".
        rec = tmp_path / "rec.mp3"
        rec.touch()
        (tmp_path / "rec.txt").touch()  # transcription succeeded
        st = self._state(tmp_path)
        stat = rec.stat()
        st.mark("rec.mp3", "error", stat.st_mtime, stat.st_size, detail="postprocess failed")

        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=False, state=st))

        assert [f.name for f in files] == ["rec.mp3"]
        assert st.lookup("rec.mp3").status == "error"

    def test_partial_row_with_existing_output_is_still_queued(self, tmp_path: Path):
        rec = tmp_path / "rec.mp3"
        rec.touch()
        (tmp_path / "rec.txt").touch()
        st = self._state(tmp_path)
        stat = rec.stat()
        st.mark("rec.mp3", "partial", stat.st_mtime, stat.st_size, detail="interrupted")

        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=False, state=st))

        assert [f.name for f in files] == ["rec.mp3"]

    def test_state_dir_is_not_walked(self, tmp_path: Path):
        (tmp_path / "rec.mp3").touch()
        hidden = tmp_path / ".whispercrawl"
        hidden.mkdir()
        (hidden / "rec.mp3").touch()  # would be a false candidate if traversed

        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=True))
        assert [f.name for f in files] == ["rec.mp3"]

    def test_db_dir_is_not_walked(self, tmp_path: Path):
        # EPIC-043: the index now lives in a `db/` directory; a `db/` under the
        # watch dir (custom state.path, or an operator's own folder) is skipped.
        (tmp_path / "rec.mp3").touch()
        db_dir = tmp_path / "db"
        db_dir.mkdir()
        (db_dir / "state.db").write_bytes(b"")
        (db_dir / "decoy.mp3").touch()  # would be a false candidate if traversed

        files = list(iter_media_files(tmp_path, EXTENSIONS, "", rescan=True))
        assert [f.name for f in files] == ["rec.mp3"]


class TestIgnoreProcessed:
    """EPIC-046: `--refresh` traversal yields every media file regardless of index/outputs."""

    def test_yields_done_and_output_bearing_files(self, tmp_path: Path):
        a, b = tmp_path / "a.mp3", tmp_path / "b.mp3"
        a.touch()
        b.touch()
        (tmp_path / "a.txt").write_text("already transcribed")
        st = ProcessingState.open(tmp_path / "state.db")
        st.mark("b.mp3", "done", b.stat().st_mtime, b.stat().st_size)

        files = list(iter_media_files(
            tmp_path, EXTENSIONS, "", rescan=False, state=st, ignore_processed=True,
        ))
        assert sorted(f.name for f in files) == ["a.mp3", "b.mp3"]

    def test_still_applies_skip_marker_and_age(self, tmp_path: Path):
        import os
        import time

        keep = tmp_path / "keep.mp3"
        keep.touch()
        skip = tmp_path / "draft_skip.mp3"
        skip.touch()
        old = tmp_path / "old.mp3"
        old.touch()
        os.utime(old, (time.time() - 40 * 86400, time.time() - 40 * 86400))

        files = list(iter_media_files(
            tmp_path, EXTENSIONS, "", rescan=False,
            skip_marker="_skip", max_age_days=10, age_basis="mtime", ignore_processed=True,
        ))
        assert [f.name for f in files] == ["keep.mp3"]


class TestDirectoryMediaFiles:
    """EPIC-059: the non-recursive per-directory census the directory-result
    rebuild is built from. Same filters as ``iter_media_files``."""

    def test_direct_media_children_sorted_non_media_ignored(self, tmp_path: Path):
        (tmp_path / "b.mp3").touch()
        (tmp_path / "a.mp3").touch()
        (tmp_path / "notes.txt").touch()
        (tmp_path / "results.html").touch()
        assert [p.name for p in directory_media_files(tmp_path, EXTENSIONS)] == ["a.mp3", "b.mp3"]

    def test_non_recursive_subdirectory_files_not_returned(self, tmp_path: Path):
        (tmp_path / "rec.mp3").touch()
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "inner.mp3").touch()
        assert [p.name for p in directory_media_files(tmp_path, EXTENSIONS)] == ["rec.mp3"]

    def test_skip_marker_and_max_age_apply(self, tmp_path: Path):
        now = time.time()
        marked = tmp_path / "rec_skip.mp3"
        marked.touch()
        os.utime(marked, (now, now))
        old = tmp_path / "old.mp3"
        old.touch()
        os.utime(old, (now - 10 * 86400, now - 10 * 86400))
        keep = tmp_path / "keep.mp3"
        keep.touch()

        files = directory_media_files(
            tmp_path, EXTENSIONS, skip_marker="_skip", max_age_days=5, age_basis="mtime",
        )
        assert [p.name for p in files] == ["keep.mp3"]

    def test_candidate_that_vanishes_before_stat_is_skipped(self, tmp_path: Path, monkeypatch):
        real_stat = Path.stat

        def flaky_stat(self, *args, **kwargs):
            if self.name == "rec.mp3":
                raise FileNotFoundError(2, "No such file or directory", str(self))
            return real_stat(self, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", flaky_stat)
        (tmp_path / "rec.mp3").touch()
        (tmp_path / "other.mp3").touch()
        assert [p.name for p in directory_media_files(tmp_path, EXTENSIONS)] == ["other.mp3"]

    def test_empty_or_missing_directory_returns_empty(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert directory_media_files(empty, EXTENSIONS) == []
        assert directory_media_files(tmp_path / "gone", EXTENSIONS) == []
