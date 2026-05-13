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

    def summarize_directory(self, dir_path: Path, file_sum_suffix: str) -> str:
        """Collect all per-file summaries in dir_path and produce a combined summary."""
        parts = []
        for summary_file in sorted(dir_path.glob(f"*{file_sum_suffix}")):
            parts.append(summary_file.read_text(encoding="utf-8"))
        if not parts:
            raise SummarizationError(f"No summary files found in {dir_path}")
        combined = "\n\n---\n\n".join(parts)
        return self._call_ollama(combined, file=str(dir_path.name))
