"""Persisted index of processed media files.

Backed by a single SQLite file so a scheduled run over a large catalog can
answer "already processed?" with an indexed lookup instead of probing the
filesystem for output files on every pass. Deleting the file is safe: the
next run re-derives ``done`` records from whichever output files exist,
without reprocessing anything.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "2"
STATE_DIRNAME = "db"
LEGACY_STATE_DIRNAME = ".whispercrawl"  # pre-EPIC-043 location, under watch_dir
STATE_FILENAME = "state.db"
_SQLITE_SIDECARS = ("-wal", "-shm", "-journal")

_MTIME_TOLERANCE = 1e-6  # seconds — filesystem mtime round-trips are not bit-exact

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path       TEXT PRIMARY KEY,
    mtime      REAL NOT NULL,
    size       INTEGER NOT NULL,
    status     TEXT NOT NULL,
    updated_at REAL NOT NULL,
    detail     TEXT NOT NULL DEFAULT '',
    steps      TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Record:
    path: str
    mtime: float
    size: int
    status: str  # "done" | "error" | "partial"
    updated_at: float
    detail: str
    steps: str = ""


class ProcessingState:
    """SQLite-backed record of which media files have been processed."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @classmethod
    def open(cls, path: Union[str, Path]) -> "ProcessingState":
        """Open (creating and migrating the schema as needed) a state file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(files)")}
        if "steps" not in columns:
            conn.execute("ALTER TABLE files ADD COLUMN steps TEXT NOT NULL DEFAULT ''")
        conn.execute(
            "INSERT INTO meta(key, value) VALUES ('schema_version', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (SCHEMA_VERSION,),
        )
        conn.commit()
        return cls(conn)

    def lookup(self, rel_path: str) -> Optional[Record]:
        row = self._conn.execute(
            "SELECT path, mtime, size, status, updated_at, detail, steps FROM files WHERE path = ?",
            (rel_path,),
        ).fetchone()
        return Record(*row) if row else None

    def completed_steps(self, rel_path: str, mtime: float, size: int) -> set:
        """Steps recorded as completed for this file's current mtime/size generation.

        Returns an empty set when there is no row, or when the stored row's
        mtime/size don't match — a changed file discards any recorded progress.
        """
        rec = self.lookup(rel_path)
        if rec is None or abs(rec.mtime - mtime) >= _MTIME_TOLERANCE or rec.size != size:
            return set()
        return {s for s in rec.steps.split(",") if s}

    def mark_step(self, rel_path: str, step: str, mtime: float, size: int) -> None:
        """Record a single pipeline step as completed for this file's attempt.

        Resets the recorded step set when the file changed since the last
        attempt (or there is none yet); otherwise adds ``step`` to it.
        """
        steps = self.completed_steps(rel_path, mtime, size)
        steps.add(step)
        self._conn.execute(
            "INSERT INTO files(path, mtime, size, status, updated_at, detail, steps) "
            "VALUES (?, ?, ?, 'partial', ?, '', ?) "
            "ON CONFLICT(path) DO UPDATE SET "
            "mtime=excluded.mtime, size=excluded.size, status='partial', "
            "updated_at=excluded.updated_at, steps=excluded.steps",
            (rel_path, mtime, size, time.time(), ",".join(sorted(steps))),
        )
        self._conn.commit()

    def is_current(self, rel_path: str, mtime: float, size: int) -> bool:
        """True when a ``done`` record exists for an unchanged file (mtime + size)."""
        rec = self.lookup(rel_path)
        return (
            rec is not None
            and rec.status == "done"
            and abs(rec.mtime - mtime) < _MTIME_TOLERANCE
            and rec.size == size
        )

    def mark(self, rel_path: str, status: str, mtime: float, size: int, detail: str = "") -> None:
        self._conn.execute(
            "INSERT INTO files(path, mtime, size, status, updated_at, detail) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(path) DO UPDATE SET "
            "mtime=excluded.mtime, size=excluded.size, status=excluded.status, "
            "updated_at=excluded.updated_at, detail=excluded.detail",
            (rel_path, mtime, size, status, time.time(), detail),
        )
        self._conn.commit()

    def forget(self, rel_path: str) -> None:
        self._conn.execute("DELETE FROM files WHERE path = ?", (rel_path,))
        self._conn.commit()

    def clear(self) -> None:
        self._conn.execute("DELETE FROM files")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "ProcessingState":
        return self

    def __exit__(self, *_) -> None:
        self.close()


class NullState:
    """No-op stand-in used when the persisted index is disabled."""

    def lookup(self, rel_path: str) -> None:
        return None

    def is_current(self, rel_path: str, mtime: float, size: int) -> bool:
        return False

    def completed_steps(self, rel_path: str, mtime: float, size: int) -> set:
        return set()

    def mark_step(self, rel_path: str, step: str, mtime: float, size: int) -> None:
        pass

    def mark(self, rel_path: str, status: str, mtime: float, size: int, detail: str = "") -> None:
        pass

    def forget(self, rel_path: str) -> None:
        pass

    def clear(self) -> None:
        pass

    def close(self) -> None:
        pass

    def __enter__(self) -> "NullState":
        return self

    def __exit__(self, *_) -> None:
        pass


State = Union[ProcessingState, NullState]


def default_state_path(config_root: Union[str, Path]) -> str:
    """Default index location: a ``db/`` directory beside the config file."""
    return str(Path(config_root) / STATE_DIRNAME / STATE_FILENAME)


def _migrate_legacy_index(resolved: Path, watch_dir: Optional[Union[str, Path]]) -> None:
    """Move a pre-EPIC-043 ``<watch_dir>/.whispercrawl/state.db`` to ``resolved``.

    Best-effort and one-time: only runs when the new path does not exist yet and
    a legacy DB does. On any failure the legacy DB is left in place and the run
    continues with a fresh index (which re-derives itself from output files).
    """
    if watch_dir is None or resolved.exists():
        return
    legacy_dir = Path(watch_dir) / LEGACY_STATE_DIRNAME
    legacy_db = legacy_dir / STATE_FILENAME
    if not legacy_db.exists():
        return
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy_db), str(resolved))
        for suffix in _SQLITE_SIDECARS:
            sidecar = legacy_db.with_name(STATE_FILENAME + suffix)
            if sidecar.exists():
                shutil.move(str(sidecar), str(resolved.with_name(STATE_FILENAME + suffix)))
        logger.info("Migrated processing index: %s -> %s", legacy_db, resolved)
        try:
            legacy_dir.rmdir()  # only succeeds if now empty
        except OSError:
            pass
    except OSError as e:
        logger.warning(
            "Could not migrate legacy processing index %s (%s); starting a fresh index at %s",
            legacy_db,
            e,
            resolved,
        )


def open_state(
    enabled: bool,
    path: Optional[Union[str, Path]],
    config_root: Union[str, Path],
    watch_dir: Optional[Union[str, Path]] = None,
) -> State:
    """Return a live ``ProcessingState`` or a ``NullState`` per config."""
    if not enabled:
        return NullState()
    resolved = Path(path) if path else Path(default_state_path(config_root))
    _migrate_legacy_index(resolved, watch_dir)
    logger.debug("Opening processing index at %s", resolved)
    return ProcessingState.open(resolved)
