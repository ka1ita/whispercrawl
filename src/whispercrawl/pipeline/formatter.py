"""Output format conversion — final pipeline step."""
from __future__ import annotations

from html import escape
from pathlib import Path


class Formatter:
    def __init__(self, output_format: str) -> None:
        self._fmt = output_format

    def format_file(self, txt_path: Path) -> Path:
        """Convert txt_path to the configured output format. Returns the final path.

        For 'txt': no-op, returns txt_path unchanged.
        For 'html': reads txt_path, writes .html with escaped content, deletes txt_path.
        """
        if self._fmt == "html":
            text = txt_path.read_text(encoding="utf-8")
            out_path = txt_path.with_suffix(".html")
            out_path.write_text(
                "<!DOCTYPE html>\n<html>\n"
                '<head><meta charset="utf-8"></head>\n'
                f"<body><pre>{escape(text)}</pre>\n</body>\n</html>",
                encoding="utf-8",
            )
            txt_path.unlink()
            return out_path
        if self._fmt == "md":
            text = txt_path.read_text(encoding="utf-8")
            out_path = txt_path.with_suffix(".md")
            out_path.write_text(text, encoding="utf-8")
            txt_path.unlink()
            return out_path
        return txt_path
