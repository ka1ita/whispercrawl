"""Structured per-request logging for whisper-asr and ollama HTTP calls."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any, Optional

from whispercrawl.config import LoggingConfig

logger = logging.getLogger(__name__)

_LOG_FILENAME = "service_requests.ndjson"


def _truncate(value: Optional[str], limit: Optional[int]) -> Optional[str]:
    if value is None or limit is None or len(value) <= limit:
        return value
    return value[:limit] + "…"


class ServiceLogger:
    """Logs each outbound HTTP call to whisper/ollama as a structured ndjson entry."""

    def __init__(self, config: LoggingConfig, watch_dir: Optional[Path] = None) -> None:
        self.config = config
        self._fh: Optional[IO[str]] = None

        if not config.requests:
            return

        log_path = self._resolve_log_path(config, watch_dir)
        if log_path:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(log_path, "a", encoding="utf-8")

    @staticmethod
    def _resolve_log_path(config: LoggingConfig, watch_dir: Optional[Path]) -> Optional[Path]:
        if config.log_file:
            return Path(config.log_file)
        if config.log_dir:
            return Path(config.log_dir) / _LOG_FILENAME
        if watch_dir:
            return watch_dir / "logs" / _LOG_FILENAME
        return None

    def log(
        self,
        *,
        service: str,
        method: str = "POST",
        url: str = "",
        params: Optional[dict] = None,
        file: str = "",
        model: str = "",
        request_body: Optional[Any] = None,
        duration_s: float,
        status_code: int,
        response_body: Optional[str] = None,
        response_size_bytes: int,
    ) -> None:
        if not self.config.requests:
            return

        limit = self.config.max_text_length

        entry: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": service,
            "method": method,
            "url": url,
            "params": params or {},
            "file": file,
            "model": model,
            "duration_s": round(duration_s, 3),
            "status_code": status_code,
            "response_size_bytes": response_size_bytes,
        }

        if request_body is not None:
            entry["request_body"] = _truncate_nested(request_body, limit)

        if response_body is not None:
            entry["response_body"] = _truncate(response_body, limit)

        logger.info("service_call %s", json.dumps(entry))
        if self._fh:
            self._fh.write(json.dumps(entry) + "\n")
            self._fh.flush()

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    def __enter__(self) -> "ServiceLogger":
        return self

    def __exit__(self, *_) -> None:
        self.close()


def _truncate_nested(obj: Any, limit: Optional[int]) -> Any:
    """Recursively truncate string leaves inside dicts/lists."""
    if isinstance(obj, str):
        return _truncate(obj, limit)
    if isinstance(obj, dict):
        return {k: _truncate_nested(v, limit) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_truncate_nested(v, limit) for v in obj]
    return obj
