"""Shared pytest fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def media_dir(tmp_path: Path) -> Path:
    """A temp directory with sample media filenames (empty files)."""
    files = [
        "meeting_ru.mp3",
        "interview_en.wav",
        "call.mp4",
        "call.txt",  # already transcribed — should be skipped in skip-processed mode
    ]
    for name in files:
        (tmp_path / name).touch()
    return tmp_path
