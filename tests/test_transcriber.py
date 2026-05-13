"""Tests for Transcriber: diarization output format and diarize_log behaviour."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from whispercrawl.config import TranscriptionConfig
from whispercrawl.pipeline.transcriber import Transcriber, TranscriptionError


def _config(**kwargs) -> TranscriptionConfig:
    defaults = dict(
        url="http://whisper:9000",
        language="ru",
        diarize=True,
        timeout=30,
    )
    defaults.update(kwargs)
    return TranscriptionConfig(**defaults)


def _response(body: str, status: int = 200) -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    r.text = body
    r.content = body.encode()
    return r


def _json_body(segments: list) -> str:
    return json.dumps({"segments": segments})


# ── diarize=False ─────────────────────────────────────────────────────────────

class TestDiarizeOff:
    def test_uses_txt_output_format(self, tmp_path):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"\x00")

        with patch("httpx.post", return_value=_response("hello")) as mock_post:
            Transcriber(_config(diarize=False)).transcribe(audio)

        assert mock_post.call_args.kwargs["params"]["output"] == "txt"

    def test_returns_raw_text(self, tmp_path):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"\x00")

        with patch("httpx.post", return_value=_response("raw transcript")):
            result = Transcriber(_config(diarize=False)).transcribe(audio)

        assert result == "raw transcript"

    def test_only_one_request_made(self, tmp_path):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"\x00")

        with patch("httpx.post", return_value=_response("text")) as mock_post:
            Transcriber(_config(diarize=False), diarize_log=True).transcribe(audio)

        assert mock_post.call_count == 1

    def test_no_diarize_json_file(self, tmp_path):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"\x00")

        with patch("httpx.post", return_value=_response("text")):
            Transcriber(_config(diarize=False), diarize_log=True).transcribe(audio)

        assert not (tmp_path / "a_diarize.json").exists()


# ── diarize=True, speaker labels present ─────────────────────────────────────

class TestDiarizeOnWithSpeakers:
    def test_uses_json_output_format(self, tmp_path):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"\x00")
        body = _json_body([{"speaker": "SPEAKER_00", "text": "hello"}])

        with patch("httpx.post", return_value=_response(body)) as mock_post:
            Transcriber(_config(diarize=True)).transcribe(audio)

        assert mock_post.call_args.kwargs["params"]["output"] == "json"

    def test_only_one_request_made(self, tmp_path):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"\x00")
        body = _json_body([{"speaker": "SPEAKER_00", "text": "hi"}])

        with patch("httpx.post", return_value=_response(body)) as mock_post:
            Transcriber(_config(diarize=True), diarize_log=True).transcribe(audio)

        assert mock_post.call_count == 1

    def test_formats_single_speaker(self, tmp_path):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"\x00")
        body = _json_body([{"speaker": "SPEAKER_00", "text": "Hello."}])

        with patch("httpx.post", return_value=_response(body)):
            result = Transcriber(_config(diarize=True)).transcribe(audio)

        assert result == "[SPEAKER_00]: Hello."

    def test_formats_multiple_speakers(self, tmp_path):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"\x00")
        body = _json_body([
            {"speaker": "SPEAKER_00", "text": "Hi."},
            {"speaker": "SPEAKER_01", "text": "Hello."},
            {"speaker": "SPEAKER_00", "text": "How are you?"},
        ])

        with patch("httpx.post", return_value=_response(body)):
            result = Transcriber(_config(diarize=True)).transcribe(audio)

        assert result == "[SPEAKER_00]: Hi.\n[SPEAKER_01]: Hello.\n[SPEAKER_00]: How are you?"

    def test_skips_empty_segment_text(self, tmp_path):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"\x00")
        body = _json_body([
            {"speaker": "SPEAKER_00", "text": "Hello."},
            {"speaker": "SPEAKER_00", "text": "   "},
            {"speaker": "SPEAKER_01", "text": "World."},
        ])

        with patch("httpx.post", return_value=_response(body)):
            result = Transcriber(_config(diarize=True)).transcribe(audio)

        assert result == "[SPEAKER_00]: Hello.\n[SPEAKER_01]: World."


# ── diarize=True, no speaker labels (HF_TOKEN missing) ───────────────────────

class TestDiarizeOnNoSpeakers:
    def test_returns_plain_text(self, tmp_path):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"\x00")
        body = _json_body([
            {"text": "First line."},
            {"text": "Second line."},
        ])

        with patch("httpx.post", return_value=_response(body)):
            result = Transcriber(_config(diarize=True)).transcribe(audio)

        assert result == "First line.\nSecond line."

    def test_warns_about_missing_hf_token(self, tmp_path, caplog):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"\x00")
        body = _json_body([{"text": "hello"}])

        with patch("httpx.post", return_value=_response(body)):
            with caplog.at_level(logging.WARNING):
                Transcriber(_config(diarize=True)).transcribe(audio)

        assert "HF_TOKEN" in caplog.text

    def test_warns_only_once_per_file(self, tmp_path, caplog):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"\x00")
        body = _json_body([{"text": "a"}, {"text": "b"}, {"text": "c"}])

        with patch("httpx.post", return_value=_response(body)):
            with caplog.at_level(logging.WARNING):
                Transcriber(_config(diarize=True)).transcribe(audio)

        hf_warnings = [r for r in caplog.records if "HF_TOKEN" in r.message]
        assert len(hf_warnings) == 1

    def test_empty_segments_returns_empty_string(self, tmp_path):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"\x00")
        body = _json_body([])

        with patch("httpx.post", return_value=_response(body)):
            result = Transcriber(_config(diarize=True)).transcribe(audio)

        assert result == ""

    def test_malformed_json_returns_raw_body_with_warning(self, tmp_path, caplog):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"\x00")

        with patch("httpx.post", return_value=_response("not json")):
            with caplog.at_level(logging.WARNING):
                result = Transcriber(_config(diarize=True)).transcribe(audio)

        assert result == "not json"
        assert "could not parse JSON" in caplog.text


# ── diarize_log sidecar file ──────────────────────────────────────────────────

class TestDiarizeLog:
    def test_sidecar_written_from_primary_response(self, tmp_path):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"\x00")
        body = _json_body([{"speaker": "SPEAKER_00", "text": "hi"}])

        with patch("httpx.post", return_value=_response(body)):
            Transcriber(_config(diarize=True), diarize_log=True).transcribe(audio)

        out = tmp_path / "a_diarize.json"
        assert out.exists()
        assert out.read_text(encoding="utf-8") == body

    def test_no_sidecar_when_flag_off(self, tmp_path):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"\x00")
        body = _json_body([{"speaker": "SPEAKER_00", "text": "hi"}])

        with patch("httpx.post", return_value=_response(body)):
            Transcriber(_config(diarize=True)).transcribe(audio)

        assert not (tmp_path / "a_diarize.json").exists()

    def test_sidecar_write_failure_does_not_raise(self, tmp_path, caplog):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"\x00")
        body = _json_body([{"speaker": "SPEAKER_00", "text": "hi"}])

        with patch("httpx.post", return_value=_response(body)):
            with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
                with caplog.at_level(logging.WARNING):
                    result = Transcriber(_config(diarize=True), diarize_log=True).transcribe(audio)

        assert result == "[SPEAKER_00]: hi"
        assert "disk full" in caplog.text


# ── error handling ────────────────────────────────────────────────────────────

class TestErrorHandling:
    def test_request_error_raises_transcription_error(self, tmp_path):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"\x00")

        with patch("httpx.post", side_effect=httpx.RequestError("timeout")):
            with pytest.raises(TranscriptionError, match="whisper request failed"):
                Transcriber(_config()).transcribe(audio)

    def test_non_200_raises_transcription_error(self, tmp_path):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"\x00")

        with patch("httpx.post", return_value=_response("error", status=500)):
            with pytest.raises(TranscriptionError, match="500"):
                Transcriber(_config(diarize=True)).transcribe(audio)

    def test_non_200_diarize_off_raises(self, tmp_path):
        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"\x00")

        with patch("httpx.post", return_value=_response("error", status=503)):
            with pytest.raises(TranscriptionError, match="503"):
                Transcriber(_config(diarize=False)).transcribe(audio)
