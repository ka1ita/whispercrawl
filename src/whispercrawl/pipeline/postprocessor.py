"""Post-processing: regex cleanup + LLM correction via ollama."""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import httpx

from whispercrawl.config import OllamaStepConfig

logger = logging.getLogger(__name__)

_TIMESTAMP_RE = re.compile(r'(\[(?:\w+ )?)(\d{2}:\d{2}:\d{2})(\])')


class PostProcessingError(Exception):
    pass


class PostProcessor:
    def __init__(
        self,
        config: OllamaStepConfig,
        regex_patterns: List[str] | None = None,
        service_logger: Optional[object] = None,
    ) -> None:
        self.config = config
        self._patterns = [re.compile(p) for p in (regex_patterns or [])]
        self._svc_log = service_logger

    def _apply_regex(self, text: str) -> str:
        for pattern in self._patterns:
            text = pattern.sub("", text)
        return text

    def _call_ollama(self, text: str) -> str:
        messages = [
            {"role": "system", "content": self.config.prompt},
            {"role": "user", "content": text},
        ]
        url = f"{self.config.url}/api/chat"
        start = time.monotonic()
        try:
            response = httpx.post(
                url,
                json={"model": self.config.model, "messages": messages, "stream": False},
                timeout=self.config.timeout,
            )
        except httpx.RequestError as exc:
            raise PostProcessingError(f"ollama request failed: {exc}") from exc
        duration = time.monotonic() - start

        if self._svc_log:
            result = response.json()["message"]["content"] if response.status_code == 200 else None
            self._svc_log.log(
                service="ollama",
                method="POST",
                url=url,
                file="",
                model=self.config.model,
                request_body={"messages": messages},
                duration_s=duration,
                status_code=response.status_code,
                response_body=result,
                response_size_bytes=len(response.content),
            )

        if response.status_code != 200:
            raise PostProcessingError(
                f"ollama returned {response.status_code}: {response.text[:200]}"
            )
        return response.json()["message"]["content"]

    @staticmethod
    def _offset_timestamps(text: str, offset: timedelta) -> str:
        offset_secs = int(offset.total_seconds())

        def _shift(m: re.Match) -> str:
            h, mi, s = map(int, m.group(2).split(':'))
            total = (h * 3600 + mi * 60 + s + offset_secs) % 86400
            nh, rem = divmod(total, 3600)
            nm, ns = divmod(rem, 60)
            return f"{m.group(1)}{nh:02d}:{nm:02d}:{ns:02d}{m.group(3)}"

        return _TIMESTAMP_RE.sub(_shift, text)

    def process(self, text: str, source_path: Path | None = None) -> str:
        if self.config.regex_enabled:
            text = self._apply_regex(text)
        if self.config.llm_enabled:
            text = self._call_ollama(text)
        if self.config.filename_timestamp_format and source_path is not None:
            stem = source_path.stem
            formats = self.config.filename_timestamp_format
            if isinstance(formats, str):
                formats = [formats]

            dt = None
            for fmt in formats:
                try:
                    dt = datetime.strptime(stem, fmt)
                    break
                except ValueError:
                    continue

            if dt is not None:
                offset = timedelta(hours=dt.hour, minutes=dt.minute, seconds=dt.second)
                text = self._offset_timestamps(text, offset)
            else:
                logger.warning(
                    "Cannot parse timestamp from filename %r using any of formats %r; skipping offset",
                    stem, formats,
                )
        return text
