"""Cleanup of output files produced by the pipeline."""
from __future__ import annotations

import logging
from pathlib import Path

from whispercrawl.config import CleanupConfig

logger = logging.getLogger(__name__)


class Cleaner:
    def __init__(self, config: CleanupConfig) -> None:
        self.config = config

    def clean(self, file_path: Path, success: bool) -> None:
        """Remove configured output files for file_path after a pipeline run."""
        if self.config.on == "success" and not success:
            return
        for suffix in self.config.targets:
            output = file_path.with_name(file_path.stem + suffix)
            if output.exists():
                output.unlink()
                logger.info("Cleaned: %s", output)
