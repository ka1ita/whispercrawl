"""Tests for filename-based absolute speaker timestamp offsetting (EPIC-036)."""
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from whispercrawl.config import OllamaStepConfig
from whispercrawl.pipeline.postprocessor import PostProcessor


def _pp(fmt: str | None = None) -> PostProcessor:
    cfg = OllamaStepConfig(
        llm_enabled=False,
        regex_enabled=False,
        filename_timestamp_format=fmt,
    )
    return PostProcessor(cfg)


TEXT = (
    "[SPEAKER_04 00:00:52] something was said\n"
    "[SPEAKER_05 00:01:53] another thing\n"
)


class TestOffsetTimestamps:
    def test_null_format_is_noop(self):
        pp = _pp(fmt=None)
        result = pp.process(TEXT, source_path=Path("2026-08-21_09_04_40.ogg"))
        assert result == TEXT

    def test_no_source_path_is_noop(self):
        pp = _pp(fmt="%Y-%m-%d_%H_%M_%S")
        result = pp.process(TEXT, source_path=None)
        assert result == TEXT

    def test_timestamps_shifted_by_start_time(self):
        # start = 09:04:40
        # 00:00:52 + 09:04:40 = 09:05:32
        # 00:01:53 + 09:04:40 = 09:06:33
        pp = _pp(fmt="%Y-%m-%d_%H_%M_%S")
        result = pp.process(TEXT, source_path=Path("2026-08-21_09_04_40.ogg"))
        assert "[SPEAKER_04 09:05:32]" in result
        assert "[SPEAKER_05 09:06:33]" in result

    def test_midnight_wrap(self):
        # start = 23:59:00, segment at 00:01:30 → 00:00:30
        text = "[SPEAKER_01 00:01:30] wrap test\n"
        pp = _pp(fmt="%Y-%m-%d_%H_%M_%S")
        result = pp.process(text, source_path=Path("2026-08-21_23_59_00.ogg"))
        assert "[SPEAKER_01 00:00:30]" in result

    def test_format_mismatch_logs_warning_and_returns_unchanged(self, caplog):
        pp = _pp(fmt="%Y-%m-%d_%H_%M_%S")
        with caplog.at_level(logging.WARNING):
            result = pp.process(TEXT, source_path=Path("unexpected_name.ogg"))
        assert result == TEXT
        assert "Cannot parse timestamp" in caplog.text

    def test_no_speaker_timestamps_in_text_is_noop(self):
        plain = "Hello world\nNo timestamps here\n"
        pp = _pp(fmt="%Y-%m-%d_%H_%M_%S")
        result = pp.process(plain, source_path=Path("2026-08-21_09_04_40.ogg"))
        assert result == plain

    def test_multiple_speakers_all_shifted(self):
        text = (
            "[SPEAKER_00 01:00:00] first\n"
            "[SPEAKER_01 01:30:00] second\n"
            "[SPEAKER_02 02:00:00] third\n"
        )
        pp = _pp(fmt="%Y-%m-%d_%H_%M_%S")
        result = pp.process(text, source_path=Path("2026-08-21_01_00_00.ogg"))
        assert "[SPEAKER_00 02:00:00]" in result
        assert "[SPEAKER_01 02:30:00]" in result
        assert "[SPEAKER_02 03:00:00]" in result

    def test_generic_word_label_shifted(self):
        text = "[XXX 00:00:52] something was said\n"
        pp = _pp(fmt="%Y-%m-%d_%H_%M_%S")
        result = pp.process(text, source_path=Path("2026-08-21_09_04_40.ogg"))
        assert "[XXX 09:05:32]" in result

    def test_bare_timestamp_no_label_shifted(self):
        text = "[00:00:52] something was said\n"
        pp = _pp(fmt="%Y-%m-%d_%H_%M_%S")
        result = pp.process(text, source_path=Path("2026-08-21_09_04_40.ogg"))
        assert "[09:05:32]" in result

    def test_offset_applied_after_regex_and_llm(self):
        """Offset runs last — after regex cleanup removes noise lines."""
        cfg = OllamaStepConfig(
            llm_enabled=False,
            regex_enabled=True,
            regex_patterns=[r"NOISE.*\n?"],
            filename_timestamp_format="%Y-%m-%d_%H_%M_%S",
        )
        pp = PostProcessor(cfg, regex_patterns=cfg.regex_patterns)
        text = "NOISE LINE\n[SPEAKER_01 00:00:10] real speech\n"
        result = pp.process(text, source_path=Path("2026-08-21_09_00_00.ogg"))
        assert "NOISE" not in result
        assert "[SPEAKER_01 09:00:10]" in result
