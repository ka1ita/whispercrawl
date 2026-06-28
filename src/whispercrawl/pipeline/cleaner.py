"""Cleanup of output files produced by the pipeline."""
from __future__ import annotations

import logging
from pathlib import Path

from whispercrawl.config import CleanupConfig

logger = logging.getLogger(__name__)


class Cleaner:
    def __init__(self, config: CleanupConfig, output_format: str = "txt") -> None:
        self.config = config
        if output_format == "html":
            self._ext = ".html"
        elif output_format == "md":
            self._ext = ".md"
        else:
            self._ext = ".txt"

    def clean(self, file_path: Path, success: bool) -> None:
        """Remove configured output files for file_path after a pipeline run."""
        if self.config.on == "success" and not success:
            return
        for suffix in self.config.targets:
            name = (
                file_path.stem + suffix
                if suffix.endswith(".json")
                else file_path.stem + suffix + self._ext
            )
            output = file_path.with_name(name)
            if output.exists():
                output.unlink()
                logger.info("Cleaned: %s", output)
