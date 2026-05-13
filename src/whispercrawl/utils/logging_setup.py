"""Application-level logging configuration."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from whispercrawl.config import LoggingConfig

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(config: LoggingConfig) -> None:
    level = getattr(logging, config.app_log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(console)

    if config.app_log_file:
        log_path = Path(config.app_log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=config.app_log_max_bytes,
            backupCount=config.app_log_backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(file_handler)
