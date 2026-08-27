"""Persisted index of processed media files.

Backed by a single SQLite file so a scheduled run over a large catalog can
answer "already processed?" with an indexed lookup instead of probing the
filesystem for output files on every pass. Deleting the file is safe: the
next run re-derives ``done`` records from whichever output files exist,
without reprocessing anything.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1"
STATE_DIRNAME = ".whispercrawl"
STATE_FILENAME = "state.db"

_MTIME_TOLERANCE = 1e-6  # seconds — filesystem mtime round-trips are not bit-exact

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path       TEXT PRIMARY KEY,
    mtime      REAL NOT NULL,
    size       INTEGER NOT NULL,
    status     TEXT NOT NULL,
    updated_at REAL NOT NULL,
    detail     TEXT NOT NULL DEFAULT ''
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
        conn.execute(
            "INSERT INTO meta(key, value) VALUES ('schema_version', ?) ON CONFLICT(key) DO NOTHING",
            (SCHEMA_VERSION,),
        )
        conn.commit()
        return cls(conn)

    def lookup(self, rel_path: str) -> Optional[Record]:
        row = self._conn.execute(
            "SELECT path, mtime, size, status, updated_at, detail FROM files WHERE path = ?",
            (rel_path,),
        ).fetchone()
        return Record(*row) if row else None

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


def default_state_path(watch_dir: Union[str, Path]) -> str:
    return str(Path(watch_dir) / STATE_DIRNAME / STATE_FILENAME)


def open_state(enabled: bool, path: Optional[Union[str, Path]], watch_dir: Path) -> State:
    """Return a live ``ProcessingState`` or a ``NullState`` per config."""
    if not enabled:
        return NullState()
    resolved = Path(path) if path else Path(default_state_path(watch_dir))
    logger.debug("Opening processing index at %s", resolved)
    return ProcessingState.open(resolved)
