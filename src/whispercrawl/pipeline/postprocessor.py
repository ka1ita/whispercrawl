"""Post-processing: regex cleanup + LLM correction via ollama."""
from __future__ import annotations

import re
import time
from typing import List, Optional

import httpx

from whispercrawl.config import OllamaStepConfig


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

    def process(self, text: str) -> str:
        if self.config.regex_enabled:
            text = self._apply_regex(text)
        if self.config.llm_enabled:
            text = self._call_ollama(text)
        return text
