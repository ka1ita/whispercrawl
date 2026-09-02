"""Cleanup of the consolidated result files produced by the pipeline."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

_ALL_EXTS = frozenset({".txt", ".md", ".html"})


class Cleaner:
    def __init__(
        self,
        output_format: str = "txt",
        engine_labels: "List[str] | None" = None,
    ) -> None:
        # Filename segments for every configured ASR engine ("" = the single
        # implicit engine); the consolidated result is removed once per segment.
        self.engine_labels = engine_labels or [""]
        if output_format == "html":
            self._ext = ".html"
        elif output_format == "md":
            self._ext = ".md"
        else:
            self._ext = ".txt"

    def clean_other_formats(self, file_path: Path, dry_run: bool = False) -> None:
        """Remove the consolidated result left by a previous run that used a
        different ``formatter.format`` extension."""
        other_exts = _ALL_EXTS - {self._ext}
        for label in self.engine_labels:
            for ext in sorted(other_exts):
                out = file_path.with_name(file_path.stem + label + ext)
                if out.exists():
                    if dry_run:
                        logger.info("Would remove stale format output: %s", out)
                    else:
                        out.unlink()
                        logger.info("Removed stale format output: %s", out)

    def clean(self, file_path: Path, success: bool) -> None:
        """Remove the consolidated result document for file_path after a
        ``--once --cleanup`` run, but only when every step for the file
        succeeded (a failed file writes no result to remove anyway)."""
        if not success:
            return
        for label in self.engine_labels:
            output = file_path.with_name(file_path.stem + label + self._ext)
            if output.exists():
                output.unlink()
                logger.info("Cleaned: %s", output)
