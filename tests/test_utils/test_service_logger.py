"""Tests for ServiceLogger."""
import json

import pytest

from whispercrawl.config import LoggingConfig
from whispercrawl.utils.service_logger import ServiceLogger, _truncate, _truncate_nested

_LOG_KWARGS = dict(
    service="whisper",
    method="POST",
    url="http://localhost:9000/asr",
    params={"task": "transcribe", "language": "ru"},
    file="call.mp3",
    model="base",
    duration_s=1.5,
    status_code=200,
    response_body="Hello world",
    response_size_bytes=1024,
)


class TestServiceLoggerDisabled:
    def test_does_not_write_when_requests_false(self, tmp_path):
        log_file = tmp_path / "calls.ndjson"
        cfg = LoggingConfig(requests=False, log_file=str(log_file))

        with ServiceLogger(cfg) as sl:
            sl.log(**_LOG_KWARGS)

        assert not log_file.exists()

    def test_no_file_and_requests_false_does_not_raise(self):
        cfg = LoggingConfig(requests=False)
        with ServiceLogger(cfg) as sl:
            sl.log(**_LOG_KWARGS)


class TestServiceLoggerEnabled:
    def test_writes_ndjson_entry_to_file(self, tmp_path):
        log_file = tmp_path / "calls.ndjson"
        cfg = LoggingConfig(requests=True, log_file=str(log_file))

        with ServiceLogger(cfg) as sl:
            sl.log(**_LOG_KWARGS)

        entry = json.loads(log_file.read_text().strip())
        assert entry["service"] == "whisper"
        assert entry["method"] == "POST"
        assert entry["url"] == "http://localhost:9000/asr"
        assert entry["params"] == {"task": "transcribe", "language": "ru"}
        assert entry["file"] == "call.mp3"
        assert entry["model"] == "base"
        assert entry["duration_s"] == 1.5
        assert entry["status_code"] == 200
        assert entry["response_body"] == "Hello world"
        assert entry["response_size_bytes"] == 1024
        assert "timestamp" in entry

    def test_appends_multiple_entries(self, tmp_path):
        log_file = tmp_path / "calls.ndjson"
        cfg = LoggingConfig(requests=True, log_file=str(log_file))

        with ServiceLogger(cfg) as sl:
            sl.log(**{**_LOG_KWARGS, "service": "whisper"})
            sl.log(**{**_LOG_KWARGS, "service": "ollama"})

        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["service"] == "whisper"
        assert json.loads(lines[1])["service"] == "ollama"

    def test_duration_is_rounded_to_three_decimals(self, tmp_path):
        log_file = tmp_path / "calls.ndjson"
        cfg = LoggingConfig(requests=True, log_file=str(log_file))

        with ServiceLogger(cfg) as sl:
            sl.log(**{**_LOG_KWARGS, "duration_s": 1.23456789})

        entry = json.loads(log_file.read_text().strip())
        assert entry["duration_s"] == 1.235

    def test_no_file_logs_to_stderr_only(self):
        cfg = LoggingConfig(requests=True, log_file=None)
        with ServiceLogger(cfg) as sl:
            sl.log(**_LOG_KWARGS)

    def test_context_manager_closes_file(self, tmp_path):
        log_file = tmp_path / "calls.ndjson"
        cfg = LoggingConfig(requests=True, log_file=str(log_file))

        sl = ServiceLogger(cfg)
        sl.log(**_LOG_KWARGS)
        sl.close()
        sl.close()  # second close should be a no-op


class TestLogDir:
    def test_log_dir_creates_directory_and_file(self, tmp_path):
        log_dir = tmp_path / "logs" / "service"
        cfg = LoggingConfig(requests=True, log_dir=str(log_dir))

        with ServiceLogger(cfg) as sl:
            sl.log(**_LOG_KWARGS)

        log_file = log_dir / "service_requests.ndjson"
        assert log_file.exists()
        entry = json.loads(log_file.read_text().strip())
        assert entry["service"] == "whisper"

    def test_log_file_takes_precedence_over_log_dir(self, tmp_path):
        log_file = tmp_path / "explicit.ndjson"
        log_dir = tmp_path / "logs"
        cfg = LoggingConfig(requests=True, log_file=str(log_file), log_dir=str(log_dir))

        with ServiceLogger(cfg) as sl:
            sl.log(**_LOG_KWARGS)

        assert log_file.exists()
        assert not (log_dir / "service_requests.ndjson").exists()

    def test_defaults_to_watch_dir_logs_subdir(self, tmp_path):
        cfg = LoggingConfig(requests=True)
        watch_dir = tmp_path / "audio"
        watch_dir.mkdir()

        with ServiceLogger(cfg, watch_dir=watch_dir) as sl:
            sl.log(**_LOG_KWARGS)

        log_file = watch_dir / "logs" / "service_requests.ndjson"
        assert log_file.exists()


class TestTruncation:
    def test_truncate_none_limit_returns_unchanged(self):
        assert _truncate("hello world", None) == "hello world"

    def test_truncate_within_limit_returns_unchanged(self):
        assert _truncate("hello", 10) == "hello"

    def test_truncate_exceeds_limit_appends_ellipsis(self):
        result = _truncate("hello world", 5)
        assert result == "hello…"
        assert len(result) == 6  # 5 chars + ellipsis

    def test_truncate_none_value_returns_none(self):
        assert _truncate(None, 10) is None

    def test_max_text_length_applied_to_response_body(self, tmp_path):
        log_file = tmp_path / "calls.ndjson"
        cfg = LoggingConfig(requests=True, log_file=str(log_file), max_text_length=5)

        with ServiceLogger(cfg) as sl:
            sl.log(**{**_LOG_KWARGS, "response_body": "Hello world long text"})

        entry = json.loads(log_file.read_text().strip())
        assert entry["response_body"] == "Hello…"

    def test_max_text_length_applied_to_request_body_text(self, tmp_path):
        log_file = tmp_path / "calls.ndjson"
        cfg = LoggingConfig(requests=True, log_file=str(log_file), max_text_length=5)

        with ServiceLogger(cfg) as sl:
            sl.log(**{
                **_LOG_KWARGS,
                "request_body": {"messages": [{"role": "user", "content": "Hello world long"}]},
            })

        entry = json.loads(log_file.read_text().strip())
        assert entry["request_body"]["messages"][0]["content"] == "Hello…"

    def test_truncate_nested_leaves_non_strings_unchanged(self):
        obj = {"count": 42, "flag": True, "text": "hello world"}
        result = _truncate_nested(obj, 5)
        assert result["count"] == 42
        assert result["flag"] is True
        assert result["text"] == "hello…"
