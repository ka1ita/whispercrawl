"""Configuration loading and validation."""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

import yaml

logger = logging.getLogger(__name__)


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

    speaker_timestamps: bool = False  # prefix each diarized segment with HH:MM:SS start time

    initial_prompt: Optional[str] = None
    vad_filter: Optional[bool] = None
    word_timestamps: Optional[bool] = None
    encode: Optional[bool] = None

    # EPIC-048 — multiple ASR engines. ``name`` is the engine's filename segment
    # and processing-index key ("" = the single implicit engine, no segment).
    # ``engines`` is meaningful only on the top-level ``transcription`` block and
    # is resolved by ``load_config`` into a non-empty list of per-engine configs.
    name: str = ""
    engines: List["TranscriptionConfig"] = field(default_factory=list)


_ENGINE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def engine_label(name: str) -> str:
    """Filename segment / index-key suffix for an engine (``""`` → no segment)."""
    return f"_{name}" if name else ""


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

    # strptime format(s) applied to filename stem to extract recording start time;
    # when set, offsets [SPEAKER_XX HH:MM:SS] timestamps by that wall-clock start time.
    # Accepts a single format string or a list of formats tried in order.
    filename_timestamp_format: Optional[Union[str, List[str]]] = None


@dataclass
class ScheduleConfig:
    cron: Optional[str] = None   # e.g. "0 * * * *"
    interval: Optional[str] = None  # e.g. "30m", "1h"


@dataclass
class CleanupConfig:
    # "" is the consolidated per-file / per-directory result (EPIC-047); the
    # rest are pre-047 scattered sidecars, swept once on upgrade.
    targets: List[str] = field(
        default_factory=lambda: ["", "_fix", "_sum", "_all", "_concat", "_diarize.json"]
    )
    on: str = "success"  # "success" | "always"


@dataclass
class DirSummarizationConfig(OllamaStepConfig):
    concat_source: str = "postprocessed"  # "postprocessed" | "original"
    underscore_prefix: bool = False        # true → output files named _<dirname>_...
    concat_suffix: str = "_concat"         # suffix label for the combined transcriptions file


@dataclass
class FormatterConfig:
    format: str = "txt"              # "txt" | "html" | "md"
    enabled: bool = True             # false = skip conversion; files stay as .txt
    speaker_style: str = "bold"      # "bold" | "italic" | "plain"
    text_placement: str = "same_line"  # "same_line" | "new_line"


@dataclass
class ResultConfig:
    """How the single per-file / per-directory result document is assembled (EPIC-047)."""
    file_sections: List[str] = field(default_factory=lambda: ["summary", "transcript"])
    dir_sections: List[str] = field(default_factory=lambda: ["summary", "transcript"])
    summary_heading: str = "Резюме"
    transcript_heading: str = "Транскрипция"
    heading_level: int = 1              # number of leading '#' on section headings
    separator: str = "\n\n"            # between rendered sections
    include_missing_headings: bool = False  # emit a section's heading even when it produced nothing


@dataclass
class StateConfig:
    enabled: bool = True             # persisted index of processed files
    path: Optional[str] = None       # default: <config dir>/db/state.db
    store_text: bool = True          # keep raw + post-processed transcript text in the index (powers --refresh)


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
    processing_mode: str = "per_file"  # "per_file" = all steps per file; "per_step" = each step across all files
    skip_marker: str = "_skip"  # skip files whose stem contains this string (case-insensitive); "" = disabled
    max_age_days: Optional[int] = None  # skip files older than this many days (mtime); None = unbounded
    max_files_per_run: Optional[int] = None  # cap files processed per run; None = unlimited
    formatter: FormatterConfig = field(default_factory=FormatterConfig)
    state: StateConfig = field(default_factory=StateConfig)

    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    postprocessing: OllamaStepConfig = field(default_factory=lambda: OllamaStepConfig(output_suffix="_fix"))
    file_summarization: OllamaStepConfig = field(default_factory=lambda: OllamaStepConfig(output_suffix="_sum"))
    dir_summarization: DirSummarizationConfig = field(default_factory=lambda: DirSummarizationConfig(output_suffix="_sum"))
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    cleanup: CleanupConfig = field(default_factory=CleanupConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    result: ResultConfig = field(default_factory=ResultConfig)


def _build(cls, d: dict):
    known = cls.__dataclass_fields__
    return cls(**{k: v for k, v in d.items() if k in known})


def load_config(path: Path) -> Config:
    """Load and parse config.yaml into a Config dataclass."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(_expand_env(f.read()))

    processing_mode = raw.get("processing_mode", "per_file")
    if processing_mode not in ("per_file", "per_step"):
        raise ValueError(f"processing_mode must be 'per_file' or 'per_step', got {processing_mode!r}")

    formatter_cfg = _build(FormatterConfig, raw.get("formatter", {}))
    if formatter_cfg.format not in ("txt", "html", "md"):
        raise ValueError(f"formatter.format must be 'txt', 'html', or 'md', got {formatter_cfg.format!r}")
    if formatter_cfg.speaker_style not in ("bold", "italic", "plain"):
        raise ValueError(f"formatter.speaker_style must be 'bold', 'italic', or 'plain', got {formatter_cfg.speaker_style!r}")
    if formatter_cfg.text_placement not in ("same_line", "new_line"):
        raise ValueError(f"formatter.text_placement must be 'same_line' or 'new_line', got {formatter_cfg.text_placement!r}")

    dir_sum_raw = raw.get("dir_summarization", {})
    dir_sum_cfg = _build(DirSummarizationConfig, dir_sum_raw)
    if dir_sum_cfg.concat_source not in ("postprocessed", "original"):
        raise ValueError(
            f"dir_summarization.concat_source must be 'postprocessed' or 'original',"
            f" got {dir_sum_cfg.concat_source!r}"
        )

    result_cfg = _build(ResultConfig, raw.get("result", {}) or {})
    _known_sections = ("summary", "transcript")
    for _attr in ("file_sections", "dir_sections"):
        bad = [s for s in getattr(result_cfg, _attr) if s not in _known_sections]
        if bad:
            raise ValueError(
                f"result.{_attr} entries must be one of {_known_sections}, got {bad!r}"
            )
    if not 1 <= result_cfg.heading_level <= 6:
        raise ValueError(
            f"result.heading_level must be between 1 and 6, got {result_cfg.heading_level!r}"
        )

    for _sect, _fld in (
        ("postprocessing", "replace_transcription"),
        ("file_summarization", "output_suffix"),
        ("dir_summarization", "concat_suffix"),
        ("dir_summarization", "output_suffix"),
    ):
        if isinstance(raw.get(_sect), dict) and _fld in raw[_sect]:
            logger.warning(
                "%s.%s is deprecated and ignored since EPIC-047 (one consolidated "
                "result file per audio file / per directory)",
                _sect, _fld,
            )

    tr_raw = dict(raw.get("transcription", {}) or {})
    engine_entries = tr_raw.pop("engines", None) or []
    transcription_cfg = _build(TranscriptionConfig, tr_raw)
    if engine_entries:
        resolved = []
        for entry in engine_entries:
            merged = {**tr_raw, **(entry or {})}
            merged.pop("engines", None)
            resolved.append(_build(TranscriptionConfig, merged))
    else:
        resolved = [_build(TranscriptionConfig, {**tr_raw, "name": ""})]
    names = [e.name for e in resolved]
    for n in names:
        if engine_entries and not n:
            raise ValueError("every transcription.engines entry needs a non-empty 'name'")
        if n and not _ENGINE_NAME_RE.match(n):
            raise ValueError(
                f"transcription engine name {n!r} must match [A-Za-z0-9._-]+"
            )
    if len(names) != len(set(names)):
        raise ValueError(f"transcription engine names must be unique, got {names!r}")
    transcription_cfg.engines = resolved

    watch_dir = Path(raw["watch_dir"])

    state_cfg = _build(StateConfig, raw.get("state", {}) or {})
    if state_cfg.path is None:
        from whispercrawl.state import default_state_path
        state_cfg.path = default_state_path(Path(path).resolve().parent)

    max_files_per_run = raw.get("max_files_per_run")
    if max_files_per_run is not None and max_files_per_run < 1:
        raise ValueError(f"max_files_per_run must be >= 1, got {max_files_per_run!r}")

    sched_raw = raw.get("schedule", {}) or {}
    return Config(
        watch_dir=watch_dir,
        extensions=[e.lower() for e in raw.get("extensions", [])],
        rescan=raw.get("rescan", False),
        processing_mode=processing_mode,
        skip_marker=raw.get("skip_marker", "_skip"),
        max_age_days=raw.get("max_age_days"),
        max_files_per_run=max_files_per_run,
        formatter=formatter_cfg,
        state=state_cfg,
        transcription=transcription_cfg,
        postprocessing=_build(OllamaStepConfig, raw.get("postprocessing", {})),
        file_summarization=_build(OllamaStepConfig, raw.get("file_summarization", {})),
        dir_summarization=dir_sum_cfg,
        schedule=_build(ScheduleConfig, sched_raw),
        cleanup=_build(CleanupConfig, raw.get("cleanup", {})),
        logging=_build(LoggingConfig, raw.get("logging", {})),
        result=result_cfg,
    )
