"""Tests for config loading — state index and max_files_per_run (EPIC-040)."""

from __future__ import annotations

from pathlib import Path

import pytest

from whispercrawl.config import load_config


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(f"watch_dir: {tmp_path}\nextensions: [.mp3]\n{body}", encoding="utf-8")
    return p


class TestStateConfig:
    def test_defaults_enabled_with_resolved_path(self, tmp_path: Path):
        cfg = load_config(_write(tmp_path, ""))
        assert cfg.state.enabled is True
        assert cfg.state.path == str(tmp_path / ".whispercrawl" / "state.db")

    def test_can_disable(self, tmp_path: Path):
        cfg = load_config(_write(tmp_path, "state:\n  enabled: false\n"))
        assert cfg.state.enabled is False

    def test_explicit_path_kept(self, tmp_path: Path):
        cfg = load_config(_write(tmp_path, "state:\n  path: /var/lib/wc/idx.db\n"))
        assert cfg.state.path == "/var/lib/wc/idx.db"
        assert cfg.state.enabled is True


class TestMaxFilesPerRun:
    def test_defaults_to_none(self, tmp_path: Path):
        cfg = load_config(_write(tmp_path, ""))
        assert cfg.max_files_per_run is None

    def test_positive_value_loads(self, tmp_path: Path):
        cfg = load_config(_write(tmp_path, "max_files_per_run: 250\n"))
        assert cfg.max_files_per_run == 250

    def test_zero_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="max_files_per_run"):
            load_config(_write(tmp_path, "max_files_per_run: 0\n"))

    def test_negative_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="max_files_per_run"):
            load_config(_write(tmp_path, "max_files_per_run: -5\n"))
