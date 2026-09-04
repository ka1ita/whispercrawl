"""Tests for config loading — state index and max_files_per_run (EPIC-040)."""

from __future__ import annotations

from pathlib import Path

import pytest

from asr_crawler.config import load_config


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(f"watch_dir: {tmp_path}\nextensions: [.mp3]\n{body}", encoding="utf-8")
    return p


class TestStateConfig:
    def test_defaults_to_resolved_path(self, tmp_path: Path):
        cfg = load_config(_write(tmp_path, ""))
        assert cfg.state.path == str(tmp_path / "db" / "state.db")
        assert not hasattr(cfg.state, "enabled")
        assert not hasattr(cfg.state, "store_text")

    def test_default_path_anchored_at_config_dir_not_watch_dir(self, tmp_path: Path):
        cfg_dir = tmp_path / "deploy"
        cfg_dir.mkdir()
        watch = tmp_path / "media"
        watch.mkdir()
        p = cfg_dir / "config.yaml"
        p.write_text(f"watch_dir: {watch}\nextensions: [.mp3]\n", encoding="utf-8")
        cfg = load_config(p)
        assert cfg.state.path == str(cfg_dir / "db" / "state.db")

    def test_stale_enabled_and_store_text_ignored_with_warning(self, tmp_path: Path, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            cfg = load_config(_write(tmp_path, "state:\n  enabled: false\n  store_text: false\n"))
        assert cfg.state.path == str(tmp_path / "db" / "state.db")
        assert "state.enabled is deprecated" in caplog.text
        assert "state.store_text is deprecated" in caplog.text

    def test_explicit_path_kept(self, tmp_path: Path):
        cfg = load_config(_write(tmp_path, "state:\n  path: /var/lib/wc/idx.db\n"))
        assert cfg.state.path == "/var/lib/wc/idx.db"


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


class TestMaxErrorCount:
    def test_defaults_to_none(self, tmp_path: Path):
        cfg = load_config(_write(tmp_path, ""))
        assert cfg.max_error_count is None

    def test_positive_value_loads(self, tmp_path: Path):
        cfg = load_config(_write(tmp_path, "max_error_count: 20\n"))
        assert cfg.max_error_count == 20

    def test_zero_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="max_error_count"):
            load_config(_write(tmp_path, "max_error_count: 0\n"))

    def test_negative_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="max_error_count"):
            load_config(_write(tmp_path, "max_error_count: -3\n"))


class TestResultConfig:
    def test_defaults(self, tmp_path: Path):
        cfg = load_config(_write(tmp_path, ""))
        assert cfg.result.file_sections == ["summary", "transcript"]
        assert cfg.result.dir_sections == ["summary", "transcript"]
        assert cfg.result.heading_level == 1
        assert cfg.result.include_missing_headings is False

    def test_custom_sections_and_headings(self, tmp_path: Path):
        cfg = load_config(_write(
            tmp_path,
            "result:\n"
            "  file_sections: [transcript]\n"
            "  summary_heading: Summary\n"
            "  heading_level: 2\n",
        ))
        assert cfg.result.file_sections == ["transcript"]
        assert cfg.result.summary_heading == "Summary"
        assert cfg.result.heading_level == 2

    def test_invalid_section_name_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="file_sections"):
            load_config(_write(tmp_path, "result:\n  file_sections: [summary, bogus]\n"))

    def test_invalid_dir_section_name_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="dir_sections"):
            load_config(_write(tmp_path, "result:\n  dir_sections: [nope]\n"))

    def test_heading_level_out_of_range_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="heading_level"):
            load_config(_write(tmp_path, "result:\n  heading_level: 7\n"))

    def test_deprecated_fields_parse_without_error(self, tmp_path: Path):
        cfg = load_config(_write(
            tmp_path,
            "postprocessing:\n  replace_transcription: true\n"
            "dir_summarization:\n  concat_suffix: _all\n  output_suffix: _sum\n"
            "file_summarization:\n  output_suffix: _sum\n",
        ))
        assert cfg is not None

    def test_cleanup_section_and_error_suffix_ignored_with_warning(self, tmp_path: Path, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            cfg = load_config(_write(
                tmp_path,
                "cleanup:\n  on: always\n  targets: ['', _fix]\n"
                "transcription:\n  error_suffix: _oops\n",
            ))
        assert not hasattr(cfg, "cleanup")
        assert not hasattr(cfg.transcription, "error_suffix")
        assert "cleanup: is deprecated and ignored since EPIC-053" in caplog.text
        assert "transcription.error_suffix is deprecated" in caplog.text


class TestTranscriptionEngines:
    def test_no_engines_key_yields_one_unnamed_engine(self, tmp_path: Path):
        cfg = load_config(_write(tmp_path, "transcription:\n  language: ru\n"))
        assert [e.name for e in cfg.transcription.engines] == [""]
        assert cfg.transcription.engines[0].language == "ru"

    def test_engines_merge_onto_base(self, tmp_path: Path):
        cfg = load_config(_write(
            tmp_path,
            "transcription:\n"
            "  timeout: 1200\n"
            "  diarize: true\n"
            "  engines:\n"
            "    - name: whisperx\n"
            "    - name: faster\n"
            "      diarize: false\n",
        ))
        engs = {e.name: e for e in cfg.transcription.engines}
        assert set(engs) == {"whisperx", "faster"}
        assert engs["whisperx"].timeout == 1200      # inherited from base
        assert engs["whisperx"].diarize is True       # inherited
        assert engs["faster"].diarize is False        # overridden
        assert engs["faster"].timeout == 1200         # still inherited

    def test_duplicate_engine_name_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="unique"):
            load_config(_write(
                tmp_path,
                "transcription:\n  engines:\n    - name: x\n    - name: x\n",
            ))

    def test_unsafe_engine_name_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="A-Za-z0-9"):
            load_config(_write(
                tmp_path,
                "transcription:\n  engines:\n    - name: 'has/slash'\n",
            ))

    def test_empty_name_with_engines_list_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="non-empty"):
            load_config(_write(
                tmp_path,
                "transcription:\n  engines:\n    - url: http://x\n",
            ))


class TestTranscriptionConcurrency:
    def test_defaults_to_one(self, tmp_path: Path):
        cfg = load_config(_write(tmp_path, ""))
        assert cfg.transcription.concurrency == 1

    def test_explicit_value_loads(self, tmp_path: Path):
        cfg = load_config(_write(tmp_path, "transcription:\n  concurrency: 3\n"))
        assert cfg.transcription.concurrency == 3

    def test_value_above_engine_count_is_allowed(self, tmp_path: Path):
        cfg = load_config(_write(
            tmp_path,
            "transcription:\n"
            "  concurrency: 9\n"
            "  engines:\n    - name: a\n    - name: b\n",
        ))
        assert cfg.transcription.concurrency == 9

    def test_zero_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="concurrency"):
            load_config(_write(tmp_path, "transcription:\n  concurrency: 0\n"))

    def test_negative_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="concurrency"):
            load_config(_write(tmp_path, "transcription:\n  concurrency: -2\n"))

    def test_not_merged_onto_per_engine_configs(self, tmp_path: Path):
        cfg = load_config(_write(
            tmp_path,
            "transcription:\n"
            "  concurrency: 4\n"
            "  engines:\n    - name: a\n    - name: b\n",
        ))
        assert all(e.concurrency == 1 for e in cfg.transcription.engines)


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
