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
        assert cfg.state.path == str(tmp_path / "db" / "state.db")

    def test_default_path_anchored_at_config_dir_not_watch_dir(self, tmp_path: Path):
        cfg_dir = tmp_path / "deploy"
        cfg_dir.mkdir()
        watch = tmp_path / "media"
        watch.mkdir()
        p = cfg_dir / "config.yaml"
        p.write_text(f"watch_dir: {watch}\nextensions: [.mp3]\n", encoding="utf-8")
        cfg = load_config(p)
        assert cfg.state.path == str(cfg_dir / "db" / "state.db")

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


class TestProcessingMode:
    def test_defaults_to_per_file(self, tmp_path: Path):
        cfg = load_config(_write(tmp_path, ""))
        assert cfg.processing_mode == "per_file"

    def test_per_step_loads(self, tmp_path: Path):
        cfg = load_config(_write(tmp_path, "processing_mode: per_step\n"))
        assert cfg.processing_mode == "per_step"

    def test_invalid_value_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="processing_mode"):
            load_config(_write(tmp_path, "processing_mode: bogus\n"))
