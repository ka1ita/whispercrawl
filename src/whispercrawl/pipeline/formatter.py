"""Output format conversion — final pipeline step."""
from __future__ import annotations

import re
from html import escape
from pathlib import Path

_SPEAKER_RE = re.compile(r'^\[([^\]]+)\]:\s*(.*)')


class Formatter:
    def __init__(
        self,
        output_format: str,
        speaker_style: str = "bold",
        text_placement: str = "same_line",
    ) -> None:
        self._fmt = output_format
        self._speaker_style = speaker_style
        self._text_placement = text_placement

    def _md_speaker_line(self, label: str, text: str) -> str:
        if self._speaker_style == "italic":
            styled = f"*[{label}]:*"
        elif self._speaker_style == "plain":
            styled = f"[{label}]:"
        else:
            styled = f"**[{label}]:**"
        return f"{styled}\n{text}" if self._text_placement == "new_line" else f"{styled} {text}"

    def _html_speaker_line(self, label: str, text: str) -> str:
        escaped_label = escape(label)
        escaped_text = escape(text)
        if self._speaker_style == "italic":
            styled = f"<em>[{escaped_label}]:</em>"
        elif self._speaker_style == "plain":
            styled = f"[{escaped_label}]:"
        else:
            styled = f"<strong>[{escaped_label}]:</strong>"
        separator = "<br>" if self._text_placement == "new_line" else " "
        return f"<p>{styled}{separator}{escaped_text}</p>"

    def _render_md(self, text: str) -> str:
        result = []
        for line in text.splitlines():
            m = _SPEAKER_RE.match(line)
            result.append(self._md_speaker_line(m.group(1), m.group(2)) if m else line)
        rendered = "\n".join(result)
        return rendered + "\n" if text.endswith("\n") else rendered

    def _render_html(self, text: str) -> str:
        lines = text.splitlines()
        has_speakers = any(_SPEAKER_RE.match(line) for line in lines)
        if not has_speakers:
            body = f"<pre>{escape(text)}</pre>"
        else:
            parts = []
            for line in lines:
                m = _SPEAKER_RE.match(line)
                if m:
                    parts.append(self._html_speaker_line(m.group(1), m.group(2)))
                elif line.strip():
                    parts.append(f"<p>{escape(line)}</p>")
            body = "\n".join(parts)
        return (
            "<!DOCTYPE html>\n<html>\n"
            '<head><meta charset="utf-8"></head>\n'
            f"<body>{body}\n</body>\n</html>"
        )

    def format_file(self, txt_path: Path) -> Path:
        """Convert txt_path to the configured output format. Returns the final path.

        For 'txt': no-op, returns txt_path unchanged.
        For 'html': reads txt_path, writes .html, deletes txt_path.
        For 'md': reads txt_path, writes .md, deletes txt_path.
        Speaker labels ([SPEAKER_XX]:) are styled per speaker_style / text_placement.
        """
        if self._fmt == "html":
            text = txt_path.read_text(encoding="utf-8")
            out_path = txt_path.with_suffix(".html")
            out_path.write_text(self._render_html(text), encoding="utf-8")
            txt_path.unlink()
            return out_path
        if self._fmt == "md":
            text = txt_path.read_text(encoding="utf-8")
            out_path = txt_path.with_suffix(".md")
            out_path.write_text(self._render_md(text), encoding="utf-8")
            txt_path.unlink()
            return out_path
        return txt_path
