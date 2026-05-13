"""Tests for Transcriber — ASR param forwarding."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from whispercrawl.config import TranscriptionConfig
from whispercrawl.pipeline.transcriber import Transcriber, TranscriptionError


def _make_audio(tmp_path: Path) -> Path:
    f = tmp_path / "sample.mp3"
    f.write_bytes(b"\x00" * 8)
    return f


def _mock_response(text: str = "hello", status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.content = text.encode()
    return resp


class TestTranscriberParamForwarding:
    def test_default_config_omits_optional_params(self, tmp_path):
        audio = _make_audio(tmp_path)
        cfg = TranscriptionConfig()

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_mock_response()) as mock_post:
            Transcriber(cfg).transcribe(audio)

        data = mock_post.call_args.kwargs["params"]
        assert "initial_prompt" not in data
        assert "vad_filter" not in data
        assert "word_timestamps" not in data
        assert "encode" not in data

    def test_initial_prompt_forwarded(self, tmp_path):
        audio = _make_audio(tmp_path)
        cfg = TranscriptionConfig(initial_prompt="Meeting transcript:")

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_mock_response()) as mock_post:
            Transcriber(cfg).transcribe(audio)

        assert mock_post.call_args.kwargs["params"]["initial_prompt"] == "Meeting transcript:"

    def test_vad_filter_forwarded_as_lowercase_string(self, tmp_path):
        audio = _make_audio(tmp_path)
        cfg = TranscriptionConfig(vad_filter=True)

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_mock_response()) as mock_post:
            Transcriber(cfg).transcribe(audio)

        assert mock_post.call_args.kwargs["params"]["vad_filter"] == "true"

    def test_word_timestamps_forwarded(self, tmp_path):
        audio = _make_audio(tmp_path)
        cfg = TranscriptionConfig(word_timestamps=False)

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_mock_response()) as mock_post:
            Transcriber(cfg).transcribe(audio)

        assert mock_post.call_args.kwargs["params"]["word_timestamps"] == "false"

    def test_encode_forwarded(self, tmp_path):
        audio = _make_audio(tmp_path)
        cfg = TranscriptionConfig(encode=True)

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_mock_response()) as mock_post:
            Transcriber(cfg).transcribe(audio)

        assert mock_post.call_args.kwargs["params"]["encode"] == "true"

    def test_all_optional_params_set(self, tmp_path):
        audio = _make_audio(tmp_path)
        cfg = TranscriptionConfig(
            initial_prompt="hint",
            vad_filter=True,
            word_timestamps=True,
            encode=False,
        )

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_mock_response()) as mock_post:
            Transcriber(cfg).transcribe(audio)

        data = mock_post.call_args.kwargs["params"]
        assert data["initial_prompt"] == "hint"
        assert data["vad_filter"] == "true"
        assert data["word_timestamps"] == "true"
        assert data["encode"] == "false"

    def test_timeout_used_from_config(self, tmp_path):
        audio = _make_audio(tmp_path)
        cfg = TranscriptionConfig(timeout=120)

        with patch("whispercrawl.pipeline.transcriber.httpx.post", return_value=_mock_response()) as mock_post:
            Transcriber(cfg).transcribe(audio)

        assert mock_post.call_args.kwargs["timeout"] == 120

    def test_request_error_raises_transcription_error(self, tmp_path):
        import httpx
        audio = _make_audio(tmp_path)
        cfg = TranscriptionConfig()

        with patch("whispercrawl.pipeline.transcriber.httpx.post", side_effect=httpx.ReadTimeout("timed out")):
            with pytest.raises(TranscriptionError, match="whisper request failed"):
                Transcriber(cfg).transcribe(audio)
