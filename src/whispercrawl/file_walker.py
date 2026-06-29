"""Recursive file discovery with skip-processed support."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Generator, List

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
) -> Generator[Path, None, None]:
    """Yield media files under root that need processing."""
    _all_exts = (".txt", ".md", ".html")
    _marker = skip_marker.lower() if skip_marker else ""
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in extensions:
            continue
        if _marker and _marker in path.stem.lower():
            logger.debug("Skipping %s — filename contains skip marker %r", path, skip_marker)
            continue
        if not rescan:
            stem = path.stem + transcription_suffix
            if any(path.with_name(stem + e).exists() for e in _all_exts):
                continue
        yield path
