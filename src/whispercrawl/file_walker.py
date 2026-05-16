"""Recursive file discovery with skip-processed support."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Generator, List

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
    output_format: str = "txt",
) -> Generator[Path, None, None]:
    """Yield media files under root that need processing."""
    ext = ".html" if output_format == "html" else ".txt"
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in extensions:
            continue
        if not rescan:
            output = path.with_name(path.stem + transcription_suffix + ext)
            if output.exists():
                continue
        yield path
