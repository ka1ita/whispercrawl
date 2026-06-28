"""Cleanup of output files produced by the pipeline."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from whispercrawl.config import CleanupConfig

logger = logging.getLogger(__name__)

_ALL_EXTS = frozenset({".txt", ".md", ".html"})


class Cleaner:
    def __init__(self, config: CleanupConfig, output_format: str = "txt") -> None:
        self.config = config
        if output_format == "html":
            self._ext = ".html"
        elif output_format == "md":
            self._ext = ".md"
        else:
            self._ext = ".txt"

    def clean_other_formats(
        self, file_path: Path, suffix_labels: List[str], dry_run: bool = False
    ) -> None:
        """Remove output files left from a previous run that used a different format extension."""
        other_exts = _ALL_EXTS - {self._ext}
        for suffix in suffix_labels:
            for ext in sorted(other_exts):
                out = file_path.with_name(file_path.stem + suffix + ext)
                if out.exists():
                    if dry_run:
                        logger.info("Would remove stale format output: %s", out)
                    else:
                        out.unlink()
                        logger.info("Removed stale format output: %s", out)

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
