"""Tests for the --errors CLI action (run_errors) — EPIC-049."""
from __future__ import annotations

from pathlib import Path

from whispercrawl.config import (
    Config,
    FormatterConfig,
    LoggingConfig,
    StateConfig,
    TranscriptionConfig,
)
from whispercrawl.main import run_errors
from whispercrawl.state import ProcessingState


def _config(tmp_path: Path, *, state_enabled: bool = True) -> Config:
    return Config(
        watch_dir=tmp_path,
        extensions=[".mp3"],
        state=StateConfig(enabled=state_enabled),
        formatter=FormatterConfig(format="txt"),
        transcription=TranscriptionConfig(output_suffix="", error_suffix="_err"),
        logging=LoggingConfig(),
    )


def test_clean_index_exits_zero(tmp_path, capsys):
    ProcessingState.open(tmp_path / "db" / "state.db").close()
    assert run_errors(_config(tmp_path)) == 0


def test_no_index_exits_zero(tmp_path):
    assert run_errors(_config(tmp_path)) == 0


def test_disabled_state_notes_and_exits_zero(tmp_path, caplog):
    with caplog.at_level("INFO"):
        assert run_errors(_config(tmp_path, state_enabled=False)) == 0
    assert "disabled" in caplog.text.lower()


def test_outstanding_errors_listed_and_exit_nonzero(tmp_path, capsys):
    db = tmp_path / "db" / "state.db"
    with ProcessingState.open(db) as st:
        st.record_error("stalin/rec.mp3", "transcribe", "HTTP 504 from :9001", engine="faster")
        st.record_error("stalin", "dir_summarize", "ollama: model not found", engine="wx", scope="dir")

    rc = run_errors(_config(tmp_path))
    out = capsys.readouterr().out

    assert rc == 1
    assert "stalin/rec.mp3" in out
    assert "[faster] transcribe" in out
    assert "HTTP 504 from :9001" in out
    assert "stalin  (directory)" in out
    assert "[wx] dir_summarize" in out


def test_multiline_message_shows_first_line(tmp_path, capsys):
    db = tmp_path / "db" / "state.db"
    with ProcessingState.open(db) as st:
        st.record_error("a.mp3", "postprocess", "boom happened\nstack trace line\nmore")

    run_errors(_config(tmp_path))
    out = capsys.readouterr().out
    assert "boom happened" in out
    assert "stack trace line" not in out
