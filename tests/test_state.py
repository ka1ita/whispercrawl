"""Tests for the persisted processing index (state.py)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from whispercrawl.state import NullState, ProcessingState, default_state_path, open_state


class TestProcessingState:
    def test_open_creates_file_and_parent(self, tmp_path: Path):
        db = tmp_path / "nested" / "state.db"
        with ProcessingState.open(db):
            pass
        assert db.exists()

    def test_mark_then_lookup(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark("a/b.mp3", "done", 123.0, 456)
            rec = st.lookup("a/b.mp3")
        assert rec is not None
        assert rec.status == "done"
        assert rec.size == 456
        assert rec.mtime == 123.0

    def test_lookup_missing_returns_none(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            assert st.lookup("nope.mp3") is None

    def test_is_current_true_on_exact_match(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark("x.mp3", "done", 1000.0, 10)
            assert st.is_current("x.mp3", 1000.0, 10) is True

    def test_is_current_false_on_changed_mtime(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark("x.mp3", "done", 1000.0, 10)
            assert st.is_current("x.mp3", 1001.0, 10) is False

    def test_is_current_false_on_changed_size(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark("x.mp3", "done", 1000.0, 10)
            assert st.is_current("x.mp3", 1000.0, 11) is False

    def test_is_current_false_when_status_not_done(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark("x.mp3", "error", 1000.0, 10)
            assert st.is_current("x.mp3", 1000.0, 10) is False

    def test_is_current_false_for_partial(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark("x.mp3", "partial", 1000.0, 10, detail="interrupted mid-pipeline")
            assert st.is_current("x.mp3", 1000.0, 10) is False
            assert st.lookup("x.mp3").status == "partial"

    def test_mark_upserts(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark("x.mp3", "error", 1.0, 1)
            st.mark("x.mp3", "done", 2.0, 2)
            rec = st.lookup("x.mp3")
        assert rec.status == "done"
        assert rec.mtime == 2.0

    def test_forget(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark("x.mp3", "done", 1.0, 1)
            st.forget("x.mp3")
            assert st.lookup("x.mp3") is None

    def test_clear(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark("a.mp3", "done", 1.0, 1)
            st.mark("b.mp3", "done", 1.0, 1)
            st.clear()
            assert st.lookup("a.mp3") is None
            assert st.lookup("b.mp3") is None

    def test_persists_across_reopen(self, tmp_path: Path):
        db = tmp_path / "s.db"
        with ProcessingState.open(db) as st:
            st.mark("x.mp3", "done", 5.0, 5)
        with ProcessingState.open(db) as st:
            assert st.is_current("x.mp3", 5.0, 5)


class TestStepResume:
    def test_mark_step_then_completed_steps(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark_step("x.mp3", "transcribe", 1.0, 10)
            assert st.completed_steps("x.mp3", 1.0, 10) == {"transcribe"}

    def test_mark_step_accumulates_for_unchanged_mtime_size(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark_step("x.mp3", "transcribe", 1.0, 10)
            st.mark_step("x.mp3", "postprocess", 1.0, 10)
            assert st.completed_steps("x.mp3", 1.0, 10) == {"transcribe", "postprocess"}

    def test_mark_step_resets_on_mtime_change(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark_step("x.mp3", "transcribe", 1.0, 10)
            st.mark_step("x.mp3", "transcribe", 2.0, 10)  # file changed, new attempt
            assert st.completed_steps("x.mp3", 2.0, 10) == {"transcribe"}
            assert st.completed_steps("x.mp3", 1.0, 10) == set()

    def test_completed_steps_empty_for_unknown_path(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            assert st.completed_steps("nope.mp3", 1.0, 1) == set()

    def test_completed_steps_empty_when_mtime_mismatches(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark_step("x.mp3", "transcribe", 1.0, 10)
            assert st.completed_steps("x.mp3", 1.5, 10) == set()

    def test_completed_steps_empty_when_size_mismatches(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark_step("x.mp3", "transcribe", 1.0, 10)
            assert st.completed_steps("x.mp3", 1.0, 11) == set()

    def test_mark_step_sets_status_partial(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark_step("x.mp3", "transcribe", 1.0, 10)
            assert st.lookup("x.mp3").status == "partial"

    def test_final_mark_done_preserves_recorded_steps(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark_step("x.mp3", "transcribe", 1.0, 10)
            st.mark_step("x.mp3", "postprocess", 1.0, 10)
            st.mark("x.mp3", "done", 1.0, 10)
            rec = st.lookup("x.mp3")
        assert rec.status == "done"
        assert set(rec.steps.split(",")) == {"transcribe", "postprocess"}

    def test_migration_from_v2_db_preserves_rows_and_adds_asr_results(self, tmp_path: Path):
        db = tmp_path / "old.db"
        conn = sqlite3.connect(str(db))
        conn.executescript(
            """
            CREATE TABLE files (
                path       TEXT PRIMARY KEY,
                mtime      REAL NOT NULL,
                size       INTEGER NOT NULL,
                status     TEXT NOT NULL,
                updated_at REAL NOT NULL,
                detail     TEXT NOT NULL DEFAULT '',
                steps      TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )
        conn.execute(
            "INSERT INTO files(path, mtime, size, status, updated_at, detail, steps) "
            "VALUES ('old.mp3', 1.0, 10, 'done', 1.0, '', 'transcribe')"
        )
        conn.execute("INSERT INTO meta(key, value) VALUES ('schema_version', '2')")
        conn.commit()
        conn.close()

        with ProcessingState.open(db) as st:
            rec = st.lookup("old.mp3")
            assert rec.status == "done"
            assert rec.steps == "transcribe"
            assert st.get_text("old.mp3", "asr", 1.0, 10) is None  # no text stored yet
            st.save_text("old.mp3", "asr", "t", 1.0, 10)
            assert st.get_text("old.mp3", "asr", 1.0, 10) == "t"  # asr_results table works


class TestTextStorage:
    def test_save_then_get_roundtrip(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.save_text("x.mp3", "asr", "raw transcript", 1.0, 10)
            st.save_text("x.mp3", "fixed", "fixed transcript", 1.0, 10)
            assert st.get_text("x.mp3", "asr", 1.0, 10) == "raw transcript"
            assert st.get_text("x.mp3", "fixed", 1.0, 10) == "fixed transcript"

    def test_get_text_none_for_unknown_path(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            assert st.get_text("nope.mp3", "asr", 1.0, 1) is None

    def test_get_text_none_on_mtime_or_size_mismatch(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.save_text("x.mp3", "asr", "t", 1.0, 10)
            assert st.get_text("x.mp3", "asr", 2.0, 10) is None
            assert st.get_text("x.mp3", "asr", 1.0, 11) is None

    def test_mark_step_reset_nulls_stored_text(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark_step("x.mp3", "transcribe", 1.0, 10)
            st.save_text("x.mp3", "asr", "old gen text", 1.0, 10)
            st.mark_step("x.mp3", "transcribe", 2.0, 10)  # file changed
            assert st.get_text("x.mp3", "asr", 2.0, 10) is None

    def test_mark_step_same_generation_keeps_text(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark_step("x.mp3", "transcribe", 1.0, 10)
            st.save_text("x.mp3", "asr", "kept", 1.0, 10)
            st.mark_step("x.mp3", "postprocess", 1.0, 10)
            assert st.get_text("x.mp3", "asr", 1.0, 10) == "kept"

    def test_final_mark_done_keeps_text_readable(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark_step("x.mp3", "transcribe", 5.0, 5)
            st.save_text("x.mp3", "asr", "body", 5.0, 5)
            st.mark("x.mp3", "done", 5.0, 5)
            assert st.get_text("x.mp3", "asr", 5.0, 5) == "body"

    def test_nullstate_get_text_none(self):
        assert NullState().get_text("x", "asr", 1.0, 1) is None
        NullState().save_text("x", "asr", "t", 1.0, 1)  # no-op, no error


class TestPerEngineText:
    """EPIC-048: named engines store text in asr_results, independent per engine."""

    def test_two_engines_are_independent(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.save_text("x.mp3", "asr", "whisperx text", 1.0, 10, engine="whisperx")
            st.save_text("x.mp3", "asr", "faster text", 1.0, 10, engine="faster")
            assert st.get_text("x.mp3", "asr", 1.0, 10, engine="whisperx") == "whisperx text"
            assert st.get_text("x.mp3", "asr", 1.0, 10, engine="faster") == "faster text"
            # the unnamed engine's column is untouched
            assert st.get_text("x.mp3", "asr", 1.0, 10) is None

    def test_engine_text_mtime_mismatch_returns_none(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.save_text("x.mp3", "asr", "t", 1.0, 10, engine="e")
            assert st.get_text("x.mp3", "asr", 2.0, 10, engine="e") is None

    def test_per_engine_step_tokens(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark_step("x.mp3", "transcribe", 1.0, 10, engine="a")
            st.mark_step("x.mp3", "transcribe", 1.0, 10, engine="b")
            st.mark_step("x.mp3", "postprocess", 1.0, 10, engine="a")
            assert st.completed_steps("x.mp3", 1.0, 10, engine="a") == {"transcribe", "postprocess"}
            assert st.completed_steps("x.mp3", 1.0, 10, engine="b") == {"transcribe"}
            assert st.completed_steps("x.mp3", 1.0, 10) == set()  # no bare tokens

    def test_mark_step_reset_drops_all_engines(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark_step("x.mp3", "transcribe", 1.0, 10, engine="a")
            st.save_text("x.mp3", "asr", "a", 1.0, 10, engine="a")
            st.save_text("x.mp3", "asr", "b", 1.0, 10, engine="b")
            st.mark_step("x.mp3", "transcribe", 2.0, 10, engine="a")  # file changed
            assert st.get_text("x.mp3", "asr", 2.0, 10, engine="a") is None
            assert st.get_text("x.mp3", "asr", 2.0, 10, engine="b") is None

    def test_v3_db_gains_asr_results_table(self, tmp_path: Path):
        db = tmp_path / "s.db"
        conn = sqlite3.connect(db)
        conn.executescript(
            "CREATE TABLE files (path TEXT PRIMARY KEY, mtime REAL NOT NULL, size INTEGER NOT NULL,"
            " status TEXT NOT NULL, updated_at REAL NOT NULL, detail TEXT NOT NULL DEFAULT '',"
            " steps TEXT NOT NULL DEFAULT '', asr_text TEXT, fixed_text TEXT);"
            "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
        )
        conn.execute("INSERT INTO files(path,mtime,size,status,updated_at) VALUES ('a.mp3',1.0,10,'done',0)")
        conn.execute("INSERT INTO meta(key,value) VALUES ('schema_version','3')")
        conn.commit()
        conn.close()

        with ProcessingState.open(db) as st:
            assert st.lookup("a.mp3").status == "done"  # existing row preserved
            st.save_text("a.mp3", "asr", "t", 1.0, 10, engine="e")
            assert st.get_text("a.mp3", "asr", 1.0, 10, engine="e") == "t"

    def test_migration_adds_steps_column_to_v1_db(self, tmp_path: Path):
        db = tmp_path / "old.db"
        conn = sqlite3.connect(str(db))
        conn.executescript(
            """
            CREATE TABLE files (
                path       TEXT PRIMARY KEY,
                mtime      REAL NOT NULL,
                size       INTEGER NOT NULL,
                status     TEXT NOT NULL,
                updated_at REAL NOT NULL,
                detail     TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )
        conn.execute(
            "INSERT INTO files(path, mtime, size, status, updated_at, detail) "
            "VALUES ('old.mp3', 1.0, 10, 'done', 1.0, '')"
        )
        conn.execute("INSERT INTO meta(key, value) VALUES ('schema_version', '1')")
        conn.commit()
        conn.close()

        with ProcessingState.open(db) as st:
            rec = st.lookup("old.mp3")
            assert rec.status == "done"
            assert rec.steps == ""
            assert st.is_current("old.mp3", 1.0, 10) is True


class TestErrorRecording:
    """EPIC-049: pipeline failures live in the index, not in _err.txt sidecars."""

    def test_record_then_get_roundtrip(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.record_error("a.mp3", "transcribe", "HTTP 500", engine="wx", mtime=1.0, size=10)
            rows = st.get_errors("a.mp3")
        assert len(rows) == 1
        r = rows[0]
        assert (r.path, r.engine, r.scope, r.step, r.message) == (
            "a.mp3", "wx", "file", "transcribe", "HTTP 500",
        )
        assert r.mtime == 1.0 and r.size == 10

    def test_dir_scoped_row(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.record_error("sub", "dir_summarize", "ollama down", scope="dir")
            rows = st.get_errors("sub")
        assert rows[0].scope == "dir"
        assert rows[0].mtime is None and rows[0].size is None

    def test_record_upserts_on_same_key(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.record_error("a.mp3", "transcribe", "first", engine="wx")
            st.record_error("a.mp3", "transcribe", "second", engine="wx")
            rows = st.get_errors("a.mp3")
        assert [r.message for r in rows] == ["second"]

    def test_get_errors_all_grouped_by_path(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.record_error("b.mp3", "transcribe", "x")
            st.record_error("a.mp3", "postprocess", "y")
            paths = [r.path for r in st.get_errors()]
        assert paths == ["a.mp3", "b.mp3"]

    def test_clear_errors_one_engine_vs_all(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.record_error("a.mp3", "transcribe", "x", engine="wx")
            st.record_error("a.mp3", "transcribe", "y", engine="fw")
            st.clear_errors("a.mp3", engine="wx")
            assert [r.engine for r in st.get_errors("a.mp3")] == ["fw"]
            st.clear_errors("a.mp3")
            assert st.get_errors("a.mp3") == []

    def test_clear_errors_is_scope_specific(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.record_error("x", "file_summarize", "f", scope="file")
            st.record_error("x", "dir_summarize", "d", scope="dir")
            st.clear_errors("x", scope="file")
            assert [r.scope for r in st.get_errors("x")] == ["dir"]

    def test_mark_step_reset_drops_error_rows(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.mark_step("a.mp3", "transcribe", 1.0, 10)
            st.record_error("a.mp3", "postprocess", "boom", mtime=1.0, size=10)
            st.mark_step("a.mp3", "transcribe", 2.0, 10)  # file changed
            assert st.get_errors("a.mp3") == []

    def test_forget_and_clear_drop_error_rows(self, tmp_path: Path):
        with ProcessingState.open(tmp_path / "s.db") as st:
            st.record_error("a.mp3", "transcribe", "x")
            st.record_error("b.mp3", "transcribe", "y")
            st.forget("a.mp3")
            assert st.get_errors("a.mp3") == []
            st.clear()
            assert st.get_errors() == []

    def test_v4_db_gains_errors_table(self, tmp_path: Path):
        db = tmp_path / "s.db"
        conn = sqlite3.connect(db)
        conn.executescript(
            "CREATE TABLE files (path TEXT PRIMARY KEY, mtime REAL NOT NULL, size INTEGER NOT NULL,"
            " status TEXT NOT NULL, updated_at REAL NOT NULL, detail TEXT NOT NULL DEFAULT '',"
            " steps TEXT NOT NULL DEFAULT '');"
            "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
            "CREATE TABLE asr_results (path TEXT NOT NULL, engine TEXT NOT NULL, kind TEXT NOT NULL,"
            " text TEXT, mtime REAL, size INTEGER, PRIMARY KEY (path, engine, kind));"
        )
        conn.execute("INSERT INTO files(path,mtime,size,status,updated_at) VALUES ('a.mp3',1.0,10,'done',0)")
        conn.execute("INSERT INTO meta(key,value) VALUES ('schema_version','4')")
        conn.commit()
        conn.close()

        with ProcessingState.open(db) as st:
            assert st.lookup("a.mp3").status == "done"  # existing row preserved
            st.record_error("a.mp3", "transcribe", "x")
            assert [r.step for r in st.get_errors("a.mp3")] == ["transcribe"]

    def test_nullstate_error_methods(self):
        ns = NullState()
        ns.record_error("x", "transcribe", "m")  # no-op, no error
        ns.clear_errors("x")
        assert ns.get_errors() == []
        assert ns.get_errors("x") == []


class TestNullState:
    def test_is_current_always_false(self):
        ns = NullState()
        assert ns.is_current("anything", 1.0, 1) is False

    def test_mark_and_clear_are_noops(self):
        ns = NullState()
        ns.mark("x", "done", 1.0, 1)
        ns.forget("x")
        ns.clear()
        ns.close()
        assert ns.lookup("x") is None

    def test_completed_steps_always_empty(self):
        ns = NullState()
        assert ns.completed_steps("x", 1.0, 1) == set()

    def test_mark_step_is_noop(self):
        ns = NullState()
        ns.mark_step("x", "transcribe", 1.0, 1)
        assert ns.completed_steps("x", 1.0, 1) == set()

    def test_context_manager(self):
        with NullState() as ns:
            assert ns.is_current("x", 1.0, 1) is False


class TestOpenState:
    def test_disabled_returns_nullstate(self, tmp_path: Path):
        st = open_state(False, None, tmp_path)
        assert isinstance(st, NullState)
        assert not (tmp_path / "db").exists()

    def test_enabled_default_path(self, tmp_path: Path):
        st = open_state(True, None, tmp_path)
        try:
            assert isinstance(st, ProcessingState)
        finally:
            st.close()
        assert (tmp_path / "db" / "state.db").exists()

    def test_enabled_explicit_path(self, tmp_path: Path):
        target = tmp_path / "custom" / "idx.db"
        st = open_state(True, str(target), tmp_path)
        st.close()
        assert target.exists()

    def test_default_state_path(self, tmp_path: Path):
        assert default_state_path(tmp_path) == str(tmp_path / "db" / "state.db")


class TestLegacyIndexMigration:
    def _seed_legacy(self, watch_dir: Path, *, sidecars: bool = False) -> Path:
        legacy = watch_dir / ".whispercrawl" / "state.db"
        with ProcessingState.open(legacy) as st:
            st.mark("a/b.mp3", "done", 123.0, 456)
        if sidecars:
            legacy.with_name("state.db-wal").write_bytes(b"")
            legacy.with_name("state.db-shm").write_bytes(b"")
        return legacy

    def test_migrates_legacy_db_to_new_location(self, tmp_path: Path):
        config_root = tmp_path / "cfg"
        watch_dir = tmp_path / "audio"
        watch_dir.mkdir()
        legacy = self._seed_legacy(watch_dir)

        st = open_state(True, None, config_root, watch_dir=watch_dir)
        try:
            assert st.is_current("a/b.mp3", 123.0, 456)
        finally:
            st.close()

        assert (config_root / "db" / "state.db").exists()
        assert not legacy.exists()
        assert not legacy.parent.exists()  # empty legacy dir removed

    def test_migrates_wal_and_shm_sidecars(self, tmp_path: Path):
        watch_dir = tmp_path / "audio"
        watch_dir.mkdir()
        legacy = self._seed_legacy(watch_dir, sidecars=True)

        target = tmp_path / "db" / "state.db"
        # migrate without opening the DB, so a clean WAL close can't delete the moved sidecars
        from whispercrawl.state import _migrate_legacy_index

        _migrate_legacy_index(target, watch_dir)

        assert target.with_name("state.db-wal").exists()
        assert target.with_name("state.db-shm").exists()
        assert not legacy.parent.exists()  # legacy dir emptied and removed

    def test_no_migration_when_new_path_exists(self, tmp_path: Path):
        watch_dir = tmp_path / "audio"
        watch_dir.mkdir()
        legacy = self._seed_legacy(watch_dir)

        target = tmp_path / "db" / "state.db"
        ProcessingState.open(target).close()  # new path already populated
        open_state(True, str(target), tmp_path, watch_dir=watch_dir).close()  # migration must be skipped

        assert legacy.exists()  # left untouched

    def test_no_legacy_no_error(self, tmp_path: Path):
        watch_dir = tmp_path / "audio"
        watch_dir.mkdir()
        st = open_state(True, None, tmp_path, watch_dir=watch_dir)
        st.close()
        assert (tmp_path / "db" / "state.db").exists()

    def test_migration_failure_falls_back_to_fresh_index(self, tmp_path: Path, monkeypatch):
        watch_dir = tmp_path / "audio"
        watch_dir.mkdir()
        self._seed_legacy(watch_dir)

        import whispercrawl.state as state_mod

        def boom(*_a, **_kw):
            raise OSError("cannot move")

        monkeypatch.setattr(state_mod.shutil, "move", boom)
        st = open_state(True, None, tmp_path, watch_dir=watch_dir)
        try:
            assert st.lookup("a/b.mp3") is None  # fresh index
        finally:
            st.close()
        assert (tmp_path / "db" / "state.db").exists()
