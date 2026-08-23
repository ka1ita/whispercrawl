"""Per-file and per-directory summarization via ollama."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import httpx

from whispercrawl.config import OllamaStepConfig


class SummarizationError(Exception):
    pass


class Summarizer:
    def __init__(
        self,
        config: OllamaStepConfig,
        service_logger: Optional[object] = None,
    ) -> None:
        self.config = config
        self._svc_log = service_logger

    def _call_ollama(self, text: str, file: str = "") -> str:
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
            raise SummarizationError(f"ollama request failed: {exc}") from exc
        duration = time.monotonic() - start

        if self._svc_log:
            result = response.json()["message"]["content"] if response.status_code == 200 else None
            self._svc_log.log(
                service="ollama",
                method="POST",
                url=url,
                file=file,
                model=self.config.model,
                request_body={"messages": messages},
                duration_s=duration,
                status_code=response.status_code,
                response_body=result,
                response_size_bytes=len(response.content),
            )

        if response.status_code != 200:
            raise SummarizationError(
                f"ollama returned {response.status_code}: {response.text[:200]}"
            )
        return response.json()["message"]["content"]

    def summarize_file(self, text: str, file: str = "") -> str:
        """Summarize a single transcription."""
        return self._call_ollama(text, file=file)

    def concat_transcriptions(self, texts_by_name: "dict[str, str]") -> str:
        """Join pre-selected transcription texts in sorted filename order with filename headers."""
        if not texts_by_name:
            raise SummarizationError("No transcription texts to concatenate")
        parts = [f"{k}\n\n{texts_by_name[k]}" for k in sorted(texts_by_name)]
        return "\n\n---\n\n".join(parts)
