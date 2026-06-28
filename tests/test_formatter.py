"""Tests for pipeline/formatter.py — Formatter class."""
from __future__ import annotations

from pathlib import Path

import pytest

from whispercrawl.pipeline.formatter import Formatter


class TestFormatterTxt:
    def test_noop_returns_same_path(self, tmp_path):
        p = tmp_path / "rec.txt"
        p.write_text("hello", encoding="utf-8")
        result = Formatter("txt").format_file(p)
        assert result == p

    def test_noop_leaves_file_unchanged(self, tmp_path):
        p = tmp_path / "rec.txt"
        p.write_text("hello", encoding="utf-8")
        Formatter("txt").format_file(p)
        assert p.read_text(encoding="utf-8") == "hello"

    def test_noop_does_not_create_html(self, tmp_path):
        p = tmp_path / "rec.txt"
        p.write_text("hello", encoding="utf-8")
        Formatter("txt").format_file(p)
        assert not (tmp_path / "rec.html").exists()


class TestFormatterHtml:
    def test_returns_html_path(self, tmp_path):
        p = tmp_path / "rec.txt"
        p.write_text("hello", encoding="utf-8")
        result = Formatter("html").format_file(p)
        assert result == tmp_path / "rec.html"

    def test_deletes_txt_file(self, tmp_path):
        p = tmp_path / "rec.txt"
        p.write_text("hello", encoding="utf-8")
        Formatter("html").format_file(p)
        assert not p.exists()

    def test_writes_html_file(self, tmp_path):
        p = tmp_path / "rec.txt"
        p.write_text("hello", encoding="utf-8")
        Formatter("html").format_file(p)
        assert (tmp_path / "rec.html").exists()

    def test_html_contains_doctype(self, tmp_path):
        p = tmp_path / "rec.txt"
        p.write_text("hello", encoding="utf-8")
        Formatter("html").format_file(p)
        assert (tmp_path / "rec.html").read_text(encoding="utf-8").startswith("<!DOCTYPE html>")

    def test_html_wraps_content_in_pre(self, tmp_path):
        p = tmp_path / "rec.txt"
        p.write_text("hello world", encoding="utf-8")
        Formatter("html").format_file(p)
        assert "<pre>hello world</pre>" in (tmp_path / "rec.html").read_text(encoding="utf-8")

    def test_html_escapes_less_than(self, tmp_path):
        p = tmp_path / "rec.txt"
        p.write_text("a < b", encoding="utf-8")
        Formatter("html").format_file(p)
        content = (tmp_path / "rec.html").read_text(encoding="utf-8")
        assert "&lt;" in content
        assert "a < b" not in content

    def test_html_escapes_ampersand(self, tmp_path):
        p = tmp_path / "rec.txt"
        p.write_text("a & b", encoding="utf-8")
        Formatter("html").format_file(p)
        assert "&amp;" in (tmp_path / "rec.html").read_text(encoding="utf-8")

    def test_html_escapes_greater_than(self, tmp_path):
        p = tmp_path / "rec.txt"
        p.write_text("a > b", encoding="utf-8")
        Formatter("html").format_file(p)
        assert "&gt;" in (tmp_path / "rec.html").read_text(encoding="utf-8")

    def test_preserves_content_through_conversion(self, tmp_path):
        p = tmp_path / "rec.txt"
        p.write_text("line1\nline2", encoding="utf-8")
        Formatter("html").format_file(p)
        assert "line1\nline2" in (tmp_path / "rec.html").read_text(encoding="utf-8")

    def test_handles_suffix_path(self, tmp_path):
        p = tmp_path / "meeting_sum.txt"
        p.write_text("summary", encoding="utf-8")
        result = Formatter("html").format_file(p)
        assert result == tmp_path / "meeting_sum.html"
        assert (tmp_path / "meeting_sum.html").exists()
        assert not p.exists()


class TestFormatterMd:
    def test_returns_md_path(self, tmp_path):
        p = tmp_path / "rec.txt"
        p.write_text("hello", encoding="utf-8")
        result = Formatter("md").format_file(p)
        assert result == tmp_path / "rec.md"

    def test_deletes_txt_file(self, tmp_path):
        p = tmp_path / "rec.txt"
        p.write_text("hello", encoding="utf-8")
        Formatter("md").format_file(p)
        assert not p.exists()

    def test_writes_md_file(self, tmp_path):
        p = tmp_path / "rec.txt"
        p.write_text("hello", encoding="utf-8")
        Formatter("md").format_file(p)
        assert (tmp_path / "rec.md").exists()

    def test_preserves_content(self, tmp_path):
        p = tmp_path / "rec.txt"
        p.write_text("line1\nline2", encoding="utf-8")
        Formatter("md").format_file(p)
        assert (tmp_path / "rec.md").read_text(encoding="utf-8") == "line1\nline2"

    def test_does_not_escape_special_chars(self, tmp_path):
        p = tmp_path / "rec.txt"
        p.write_text("a < b & c", encoding="utf-8")
        Formatter("md").format_file(p)
        assert (tmp_path / "rec.md").read_text(encoding="utf-8") == "a < b & c"

    def test_handles_suffix_path(self, tmp_path):
        p = tmp_path / "meeting_sum.txt"
        p.write_text("summary", encoding="utf-8")
        result = Formatter("md").format_file(p)
        assert result == tmp_path / "meeting_sum.md"
        assert (tmp_path / "meeting_sum.md").exists()
        assert not p.exists()

    def test_txt_and_html_unaffected(self, tmp_path):
        p_txt = tmp_path / "a.txt"
        p_txt.write_text("x", encoding="utf-8")
        assert Formatter("txt").format_file(p_txt) == p_txt
        assert p_txt.exists()
        assert not (tmp_path / "a.md").exists()

        p_html = tmp_path / "b.txt"
        p_html.write_text("y", encoding="utf-8")
        result = Formatter("html").format_file(p_html)
        assert result.suffix == ".html"
        assert not (tmp_path / "b.md").exists()
