"""Unit tests for the result composer (EPIC-047)."""
from __future__ import annotations

from asr_crawler.config import ResultConfig
from asr_crawler.pipeline.composer import compose

HEADINGS = {"summary": "Резюме", "transcript": "Транскрипция"}


def _compose(bodies, cfg=None, sections=("summary", "transcript")):
    return compose(list(sections), bodies, HEADINGS, cfg or ResultConfig())


class TestSingleSection:
    def test_only_transcript_is_emitted_bare(self):
        assert _compose({"summary": "", "transcript": "hello world"}) == "hello world"

    def test_only_summary_is_emitted_bare(self):
        assert _compose({"summary": "just a summary", "transcript": ""}) == "just a summary"

    def test_blank_body_is_dropped(self):
        assert _compose({"summary": "   \n ", "transcript": "body"}) == "body"

    def test_nothing_present_returns_empty(self):
        assert _compose({"summary": "", "transcript": ""}) == ""

    def test_none_body_is_dropped(self):
        assert _compose({"summary": None, "transcript": "body"}) == "body"


class TestMultipleSections:
    def test_both_sections_get_headings_in_order(self):
        out = _compose({"summary": "S", "transcript": "T"})
        assert out == "# Резюме\n\nS\n\n# Транскрипция\n\nT"

    def test_section_order_follows_the_sections_list(self):
        out = _compose({"summary": "S", "transcript": "T"}, sections=("transcript", "summary"))
        assert out.index("Транскрипция") < out.index("Резюме")

    def test_heading_level_controls_hashes(self):
        out = _compose({"summary": "S", "transcript": "T"}, ResultConfig(heading_level=3))
        assert out.startswith("### Резюме")

    def test_custom_separator(self):
        out = _compose({"summary": "S", "transcript": "T"}, ResultConfig(separator="\n<hr>\n"))
        assert "\n<hr>\n" in out


class TestIncludeMissingHeadings:
    def test_missing_section_heading_emitted_when_requested(self):
        out = _compose(
            {"summary": "", "transcript": "T"},
            ResultConfig(include_missing_headings=True),
        )
        assert out == "# Резюме\n\n# Транскрипция\n\nT"

    def test_missing_headings_off_keeps_single_body_bare(self):
        out = _compose(
            {"summary": "", "transcript": "T"},
            ResultConfig(include_missing_headings=False),
        )
        assert out == "T"


class TestSectionsFilter:
    def test_section_not_in_list_is_ignored(self):
        out = _compose({"summary": "S", "transcript": "T"}, sections=("transcript",))
        assert out == "T"
