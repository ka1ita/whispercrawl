"""Assemble one result document from ordered sections (EPIC-047).

A per-file result is ``summary`` + ``transcript``; a per-directory result is
``summary`` + the concatenated transcripts. Sections are emitted as
markdown-style ``#`` headings so the ``md`` formatter passes them through and
the ``html`` formatter renders them as ``<h1>``…; ``txt`` keeps them literal.
"""
from __future__ import annotations

from asr_crawler.config import ResultConfig

KNOWN_SECTIONS = ("summary", "transcript")


def compose(
    sections: list[str],
    bodies: "dict[str, str | None]",
    headings: "dict[str, str]",
    cfg: ResultConfig,
) -> str:
    """Join the named ``sections`` (in order) into one document.

    ``bodies`` maps a section name to its text (``None``/blank → the section is
    dropped). A single surviving section is emitted without a heading unless
    ``cfg.include_missing_headings`` is set; two or more are each given their
    ``headings`` entry.
    """
    hashes = "#" * max(1, cfg.heading_level)
    present = [s for s in sections if (bodies.get(s) or "").strip()]

    if not cfg.include_missing_headings and len(present) <= 1:
        return (bodies.get(present[0]) or "").strip() if present else ""

    blocks: list[str] = []
    for name in sections:
        body = (bodies.get(name) or "").strip()
        if not body and not cfg.include_missing_headings:
            continue
        head = headings.get(name, name)
        block = f"{hashes} {head}" + (f"\n\n{body}" if body else "")
        blocks.append(block)
    return cfg.separator.join(blocks)
