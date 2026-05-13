"""Tests for setup_logging."""
import logging

import pytest

from whispercrawl.config import LoggingConfig
from whispercrawl.utils.logging_setup import setup_logging


def _handler_types(logger):
    return [type(h).__name__ for h in logger.handlers]


class TestConsoleOnly:
    def test_console_handler_always_attached(self):
        setup_logging(LoggingConfig())
        root = logging.getLogger()
        assert "StreamHandler" in _handler_types(root)

    def test_no_file_handler_when_app_log_file_absent(self):
        setup_logging(LoggingConfig())
        root = logging.getLogger()
        assert "RotatingFileHandler" not in _handler_types(root)

    def test_does_not_duplicate_handlers_on_repeated_calls(self):
        setup_logging(LoggingConfig())
        setup_logging(LoggingConfig())
        root = logging.getLogger()
        stream_count = sum(1 for h in root.handlers if type(h).__name__ == "StreamHandler")
        assert stream_count == 1


class TestFileHandler:
    def test_file_handler_attached_when_app_log_file_set(self, tmp_path):
        log_file = tmp_path / "app.log"
        setup_logging(LoggingConfig(app_log_file=str(log_file)))
        root = logging.getLogger()
        assert "RotatingFileHandler" in _handler_types(root)

    def test_log_file_written(self, tmp_path):
        log_file = tmp_path / "app.log"
        setup_logging(LoggingConfig(app_log_file=str(log_file)))
        logging.getLogger("test.epic10").info("hello from test")
        assert log_file.exists()
        assert "hello from test" in log_file.read_text(encoding="utf-8")

    def test_parent_directory_created_automatically(self, tmp_path):
        log_file = tmp_path / "subdir" / "nested" / "app.log"
        setup_logging(LoggingConfig(app_log_file=str(log_file)))
        assert log_file.parent.exists()

    def test_rotation_params_applied(self, tmp_path):
        log_file = tmp_path / "app.log"
        setup_logging(LoggingConfig(
            app_log_file=str(log_file),
            app_log_max_bytes=1024,
            app_log_backup_count=3,
        ))
        root = logging.getLogger()
        fh = next(h for h in root.handlers if type(h).__name__ == "RotatingFileHandler")
        assert fh.maxBytes == 1024
        assert fh.backupCount == 3


class TestLogLevel:
    def test_info_level_by_default(self):
        setup_logging(LoggingConfig())
        assert logging.getLogger().level == logging.INFO

    def test_debug_level_applied(self):
        setup_logging(LoggingConfig(app_log_level="DEBUG"))
        assert logging.getLogger().level == logging.DEBUG

    def test_warning_level_applied(self):
        setup_logging(LoggingConfig(app_log_level="WARNING"))
        assert logging.getLogger().level == logging.WARNING

    def test_unknown_level_falls_back_to_info(self):
        setup_logging(LoggingConfig(app_log_level="NOTALEVEL"))
        assert logging.getLogger().level == logging.INFO
