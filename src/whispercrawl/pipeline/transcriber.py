"""Transcription and diarization via whisper-asr-webservice."""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

import httpx

from whispercrawl.config import TranscriptionConfig
from whispercrawl.file_walker import detect_language

logger = logging.getLogger(__name__)

# Some whisper-asr-webservice versions (whisperx engine) prepend the speaker tag
# to each segment's `text` field in addition to the separate `speaker` key. We
# format our own label, so strip a leading '[SPEAKER_xx]:' / '[SPEAKER_xx]' here.
_EMBEDDED_SPEAKER_RE = re.compile(r"^\s*\[SPEAKER_[0-9A-Za-z_]+\]\s*:?\s*")


def _strip_embedded_speaker(text: str) -> str:
    """Remove a leading '[SPEAKER_xx]:' tag the service embeds in segment text."""
    while True:
        stripped = _EMBEDDED_SPEAKER_RE.sub("", text, count=1)
        if stripped == text:
            return text
        text = stripped


class TranscriptionError(Exception):
    pass


class Transcriber:
    def __init__(
        self,
        config: TranscriptionConfig,
        service_logger: Optional[object] = None,
        diarize_log: bool = False,
        diarize_dir: Optional[Path] = None,
        watch_dir: Optional[Path] = None,
    ) -> None:
        self.config = config
        self._svc_log = service_logger
        self._diarize_log = diarize_log
        # When set, raw diarization JSON is written under this directory mirroring
        # the file's path relative to watch_dir, instead of beside the audio.
        self._diarize_dir = Path(diarize_dir) if diarize_dir is not None else None
        self._watch_dir = Path(watch_dir) if watch_dir is not None else None

    def transcribe(self, file_path: Path) -> str:
        """Call whisper API and return transcription text.

        When diarize=True, requests output=json and formats segments with
        speaker labels: '[SPEAKER_00]: text'. Warns if no speaker labels are
        present (typically means HF_TOKEN is not configured).
        """
        language = detect_language(file_path.stem, self.config.language)

        # Use json output when diarizing so we can extract speaker labels.
        output_format = "json" if self.config.diarize else "txt"
        params: dict = {
            "task": "transcribe",
            "language": language,
            "output": output_format,
            "diarize": str(self.config.diarize).lower(),
        }
        if self.config.initial_prompt is not None:
            params["initial_prompt"] = self.config.initial_prompt
        if self.config.vad_filter is not None:
            params["vad_filter"] = str(self.config.vad_filter).lower()
        if self.config.word_timestamps is not None:
            params["word_timestamps"] = str(self.config.word_timestamps).lower()
        if self.config.encode is not None:
            params["encode"] = str(self.config.encode).lower()

        with open(file_path, "rb") as f:
            start = time.monotonic()
            try:
                response = httpx.post(
                    f"{self.config.url}/asr",
                    params=params,
                    files={"audio_file": (file_path.name, f)},
                    timeout=self.config.timeout,
                )
            except httpx.RequestError as exc:
                raise TranscriptionError(f"whisper request failed: {exc}") from exc
            duration = time.monotonic() - start

        if self._svc_log:
            self._svc_log.log(
                service="whisper",
                method="POST",
                url=f"{self.config.url}/asr",
                params=params,
                file=file_path.name,

                duration_s=duration,
                status_code=response.status_code,
                response_body=response.text if response.status_code == 200 else None,
                response_size_bytes=len(response.content),
            )

        if response.status_code != 200:
            raise TranscriptionError(
                f"whisper returned {response.status_code}: {response.text[:200]}"
            )

        if self.config.diarize:
            if self._diarize_log:
                self._save_diarize_json(file_path, response.text)
            return self._format_diarized(response.text, file_path.name)

        return response.text

    def _format_diarized(self, json_body: str, filename: str) -> str:
        """Parse JSON response segments and format with speaker labels."""
        try:
            data = json.loads(json_body)
            segments = data.get("segments", [])
        except (json.JSONDecodeError, AttributeError, TypeError):
            logger.warning(
                "diarize: could not parse JSON response for %s — returning raw body",
                filename,
            )
            return json_body

        if not segments:
            return ""

        has_speakers = any("speaker" in s for s in segments)
        if not has_speakers:
            logger.warning(
                "diarize: no speaker labels in response for %s — "
                "whisperx requires HF_TOKEN for speaker diarization; "
                "set HF_TOKEN in your environment and restart the whisper container",
                filename,
            )
            cleaned = (
                _strip_embedded_speaker(s.get("text", "").strip()).strip()
                for s in segments
            )
            return "\n".join(t for t in cleaned if t)

        lines = []
        for seg in segments:
            text = _strip_embedded_speaker(seg.get("text", "").strip()).strip()
            if not text:
                continue
            speaker = seg.get("speaker", "UNKNOWN")
            if self.config.speaker_timestamps:
                start = seg.get("start")
                if isinstance(start, (int, float)):
                    total = int(start)
                    ts = f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"
                    lines.append(f"[{speaker} {ts}] {text}")
                else:
                    lines.append(f"[{speaker}] {text}")
            else:
                lines.append(f"[{speaker}]: {text}")
        return "\n".join(lines)

    def _diarize_json_path(self, file_path: Path) -> Path:
        """Where the raw diarization JSON goes.

        With ``diarize_dir`` set: ``<diarize_dir>/<path relative to watch_dir>``
        with the audio suffix replaced by ``.json`` (subdirectories preserved).
        Otherwise the legacy sidecar beside the audio: ``<stem>_diarize.json``.
        """
        if self._diarize_dir is None:
            return file_path.with_name(file_path.stem + "_diarize.json")
        rel: Path
        if self._watch_dir is not None:
            try:
                rel = file_path.resolve().relative_to(self._watch_dir.resolve())
            except ValueError:
                rel = Path(file_path.name)
        else:
            rel = Path(file_path.name)
        return self._diarize_dir / rel.with_suffix(".json")

    def _save_diarize_json(self, file_path: Path, json_body: str) -> None:
        """Save JSON diarization response body to a file (best-effort)."""
        out = self._diarize_json_path(file_path)
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json_body, encoding="utf-8")
            logger.info("Diarize log written: %s", out)
        except Exception as exc:
            logger.warning("diarize_log: failed to write %s: %s", out.name, exc)
