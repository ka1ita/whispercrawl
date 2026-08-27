"""Tests for the persisted processing index (state.py)."""

from __future__ import annotations

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

    def test_context_manager(self):
        with NullState() as ns:
            assert ns.is_current("x", 1.0, 1) is False


class TestOpenState:
    def test_disabled_returns_nullstate(self, tmp_path: Path):
        st = open_state(False, None, tmp_path)
        assert isinstance(st, NullState)
        assert not (tmp_path / ".whispercrawl").exists()

    def test_enabled_default_path(self, tmp_path: Path):
        st = open_state(True, None, tmp_path)
        try:
            assert isinstance(st, ProcessingState)
        finally:
            st.close()
        assert (tmp_path / ".whispercrawl" / "state.db").exists()

    def test_enabled_explicit_path(self, tmp_path: Path):
        target = tmp_path / "custom" / "idx.db"
        st = open_state(True, str(target), tmp_path)
        st.close()
        assert target.exists()

    def test_default_state_path(self, tmp_path: Path):
        assert default_state_path(tmp_path) == str(tmp_path / ".whispercrawl" / "state.db")
