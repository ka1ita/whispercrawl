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
