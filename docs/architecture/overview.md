# Architecture Overview

## System Context

WhisperCrawl  runs as a scheduled Python process on the local filesystem. It has no inbound network interface — it communicates outbound only to two external services.

```
┌─────────────────────────────────────────────┐
│              WhisperCrawl                    │
│                                             │
│  FileWalker → Pipeline → OutputWriter       │
│       ↑                                     │
│  Scheduler                                  │
└────────────┬──────────────┬─────────────────┘
             │              │
    ┌────────▼────┐  ┌──────▼──────┐
    │  whisper-   │  │   ollama    │
    │ asr-webservice│  │             │
    └─────────────┘  └─────────────┘
```

## Component Responsibilities

### `file_walker.py`
Recursively scans the configured directory for audio/video files. Supports two modes:
- **skip-processed**: skip files that already have a corresponding `.txt` output
- **full-rescan**: process all matching files regardless

### `pipeline/`
Stateless processing steps, each taking a file path and returning text content:

| Module | Input | Output file suffix |
|---|---|---|
| `transcriber.py` | audio/video path | `.txt` (configurable) |
| `postprocessor.py` | `.txt` content | `_fix.txt` (configurable) |
| `summarizer.py` (per-file) | `_fix.txt` content | `_sum.txt` (configurable) |
| `summarizer.py` (per-dir) | all `_sum.txt` in dir | `<dirname>_sum.txt` |

### `config.py`
Loads and validates `config.yaml`. Exposes a single `Config` dataclass used throughout the app. See [config.yaml](../../config.yaml).

### `scheduler.py`
Wraps the main pipeline run in a cron-style schedule (APScheduler or similar). Also supports one-shot invocation via CLI flag.

### `main.py`
CLI entry point. Parses args, loads config, starts scheduler or runs once.

## File Output Conventions

- Output files sit **beside** the source audio/video file
- A file is only written on **success** — partial/error state writes `_err.txt`
- Language is inferred from filename suffix `_ru`/`_en`/`_auto`; falls back to config default

## Error Handling Strategy

Each pipeline step catches its own exceptions and writes `<source>_err.txt` with the error detail. The pipeline continues to the next file — a single failure does not halt the run.
