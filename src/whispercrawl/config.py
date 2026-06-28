"""Configuration loading and validation."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml


def _expand_env(text: str) -> str:
    """Expand ${VAR:default} placeholders, then plain $VAR / ${VAR} via os.path.expandvars."""
    def _replace(m: re.Match) -> str:
        return os.environ.get(m.group(1), m.group(2))
    text = re.sub(r'\$\{(\w+):([^}]*)\}', _replace, text)
    return os.path.expandvars(text)


@dataclass
class TranscriptionConfig:
    url: str = "http://localhost:9000"
    language: str = "auto"
    diarize: bool = False
    output_suffix: str = ""
    error_suffix: str = "_err"
    timeout: int = 300

    initial_prompt: Optional[str] = None
    vad_filter: Optional[bool] = None
    word_timestamps: Optional[bool] = None
    encode: Optional[bool] = None


@dataclass
class OllamaStepConfig:
    url: str = "http://localhost:11434"
    model: str = "llama3.2"
    prompt: str = ""
    output_suffix: str = "_fix"
    error_suffix: str = "_err"
    llm_enabled: bool = True    # controls LLM correction step
    regex_enabled: bool = True  # controls regex cleanup pass
    replace_transcription: bool = False  # move _fix over transcript after success
    regex_patterns: List[str] = field(default_factory=list)
    timeout: int = 300
    summarize_source: str = "postprocessed"  # "postprocessed" (_fix) | "original" (transcript)


@dataclass
class ScheduleConfig:
    cron: Optional[str] = None   # e.g. "0 * * * *"
    interval: Optional[str] = None  # e.g. "30m", "1h"


@dataclass
class CleanupConfig:
    targets: List[str] = field(default_factory=lambda: ["", "_fix", "_sum", "_diarize.json"])
    on: str = "success"  # "success" | "always"


@dataclass
class FormatterConfig:
    format: str = "txt"              # "txt" | "html" | "md"
    enabled: bool = True             # false = skip conversion; files stay as .txt
    speaker_style: str = "bold"      # "bold" | "italic" | "plain"
    text_placement: str = "same_line"  # "same_line" | "new_line"


@dataclass
class LoggingConfig:
    requests: bool = False
    diarize_log: bool = False            # save raw JSON diarization response to <file>_diarize.json
    log_file: Optional[str] = None       # explicit path override
    log_dir: Optional[str] = None        # directory; writes service_requests.ndjson inside
    max_text_length: Optional[int] = None  # truncate request/response text fields (None = unlimited)
    app_log_file: Optional[str] = None   # application log file path (console-only when absent)
    app_log_level: str = "INFO"          # DEBUG | INFO | WARNING | ERROR
    app_log_max_bytes: int = 10_485_760  # 10 MB per file
    app_log_backup_count: int = 5        # number of rotated backups to keep


@dataclass
class Config:
    watch_dir: Path
    extensions: List[str]
    rescan: bool = False  # False = skip-processed, True = full rescan
    formatter: FormatterConfig = field(default_factory=FormatterConfig)

    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    postprocessing: OllamaStepConfig = field(default_factory=lambda: OllamaStepConfig(output_suffix="_fix"))
    file_summarization: OllamaStepConfig = field(default_factory=lambda: OllamaStepConfig(output_suffix="_sum"))
    dir_summarization: OllamaStepConfig = field(default_factory=lambda: OllamaStepConfig(output_suffix="_sum"))
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    cleanup: CleanupConfig = field(default_factory=CleanupConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def _build(cls, d: dict):
    known = cls.__dataclass_fields__
    return cls(**{k: v for k, v in d.items() if k in known})


def load_config(path: Path) -> Config:
    """Load and parse config.yaml into a Config dataclass."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(_expand_env(f.read()))

    formatter_cfg = _build(FormatterConfig, raw.get("formatter", {}))
    if formatter_cfg.format not in ("txt", "html", "md"):
        raise ValueError(f"formatter.format must be 'txt', 'html', or 'md', got {formatter_cfg.format!r}")
    if formatter_cfg.speaker_style not in ("bold", "italic", "plain"):
        raise ValueError(f"formatter.speaker_style must be 'bold', 'italic', or 'plain', got {formatter_cfg.speaker_style!r}")
    if formatter_cfg.text_placement not in ("same_line", "new_line"):
        raise ValueError(f"formatter.text_placement must be 'same_line' or 'new_line', got {formatter_cfg.text_placement!r}")

    sched_raw = raw.get("schedule", {}) or {}
    return Config(
        watch_dir=Path(raw["watch_dir"]),
        extensions=[e.lower() for e in raw.get("extensions", [])],
        rescan=raw.get("rescan", False),
        formatter=formatter_cfg,
        transcription=_build(TranscriptionConfig, raw.get("transcription", {})),
        postprocessing=_build(OllamaStepConfig, raw.get("postprocessing", {})),
        file_summarization=_build(OllamaStepConfig, raw.get("file_summarization", {})),
        dir_summarization=_build(OllamaStepConfig, raw.get("dir_summarization", {})),
        schedule=_build(ScheduleConfig, sched_raw),
        cleanup=_build(CleanupConfig, raw.get("cleanup", {})),
        logging=_build(LoggingConfig, raw.get("logging", {})),
    )
