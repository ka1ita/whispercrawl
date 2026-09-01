"""Recursive file discovery with skip-processed support."""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Generator, List, Optional

from whispercrawl.state import LEGACY_STATE_DIRNAME, STATE_DIRNAME, State

logger = logging.getLogger(__name__)

LANGUAGE_SUFFIX_RE = re.compile(r"_(ru|en|auto)$", re.IGNORECASE)

LANGUAGE_MAP = {"ru": "ru", "en": "en", "auto": "auto"}


def detect_language(stem: str, default: str) -> str:
    """Extract language from filename stem, e.g. 'meeting_ru' -> 'ru'."""
    m = LANGUAGE_SUFFIX_RE.search(stem)
    return LANGUAGE_MAP[m.group(1).lower()] if m else default


def iter_media_files(
    root: Path,
    extensions: List[str],
    transcription_suffix: str,
    rescan: bool,
    output_format: str = "txt",  # kept for API compatibility; skip check covers all formats
    skip_marker: str = "",
    max_age_days: Optional[int] = None,
    state: Optional[State] = None,
    ignore_processed: bool = False,
    engine_labels: Optional[List[str]] = None,
) -> Generator[Path, None, None]:
    """Yield media files under root that need processing, newest first.

    When ``state`` is supplied and ``rescan`` is False, files recorded as
    ``done`` (with unchanged mtime + size) are skipped without probing the
    filesystem for output files. A file that is not in the index but already
    has an output file is recorded as ``done`` and skipped — back-filling the
    index for a pre-existing catalog with no reprocessing.

    ``ignore_processed`` (used by ``--refresh``) yields every media file that
    survives the ``skip_marker`` / ``max_age_days`` filters regardless of index
    state or existing outputs — the index skip and back-fill are bypassed.
    """
    _all_exts = (".txt", ".md", ".html")
    _elabels = engine_labels or [""]
    _marker = skip_marker.lower() if skip_marker else ""
    _cutoff = time.time() - max_age_days * 86400 if max_age_days is not None else None

    candidates: List[tuple] = []
    for path in root.rglob("*"):
        if STATE_DIRNAME in path.parts or LEGACY_STATE_DIRNAME in path.parts:
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() not in extensions:
            continue
        if _marker and _marker in path.stem.lower():
            logger.debug("Skipping %s — filename contains skip marker %r", path, skip_marker)
            continue
        st = path.stat()
        mtime, size = st.st_mtime, st.st_size
        if _cutoff is not None and mtime < _cutoff:
            logger.debug("Skipping %s — older than max_age_days=%s", path, max_age_days)
            continue
        if not rescan and not ignore_processed:
            rel = str(path.relative_to(root))
            if state is not None and state.is_current(rel, mtime, size):
                logger.debug("Skipping %s — recorded as processed in the index", path)
                continue
            # Only back-fill "done" from output existence for files with no state
            # row at all (a pre-existing catalog being indexed for the first time).
            # A file with a recorded but non-current row (error/partial/stale) must
            # still be queued so it can resume from its recorded pipeline steps —
            # otherwise an earlier step's leftover output would silently erase the
            # recorded error and the file would never be retried.
            if state is None or state.lookup(rel) is None:
                def _has_output(label: str) -> bool:
                    stem = path.stem + label + transcription_suffix
                    return any(path.with_name(stem + e).exists() for e in _all_exts)
                if all(_has_output(label) for label in _elabels):
                    if state is not None:
                        state.mark(rel, "done", mtime, size, detail="back-filled from output file")
                    continue
        candidates.append((mtime, path))

    candidates.sort(key=lambda item: item[0], reverse=True)
    for _, path in candidates:
        yield path
