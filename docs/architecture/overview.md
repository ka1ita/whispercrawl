# Architecture Overview

## System Context

WhisperCrawl runs as a scheduled Python process on the local filesystem. It has no inbound network interface — it communicates outbound only to two external services.

```
┌─────────────────────────────────────────────┐
│              WhisperCrawl                    │
│                                             │
│  FileWalker → Pipeline → Formatter          │
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

- **skip-processed**: skip files that already have a corresponding output file (`<stem>.txt`, `<stem>.md`, or `<stem>.html` — any supported format). This means changing `formatter.format` between runs will not re-trigger processing for files that already have output in any format.
- **full-rescan** (`rescan: true`): process all matching files regardless of existing output.

### `pipeline/`

All pipeline steps write plain `.txt` files internally. The Formatter runs last and converts to the final output format.

| Module | Input | Output file suffix |
|---|---|---|
| `transcriber.py` | audio/video path | `<suffix>.txt` (configurable label, default `""`) |
| `postprocessor.py` | `<suffix>.txt` content | `_fix.txt` (configurable) |
| `summarizer.py` (per-file) | `_fix.txt` content | `_sum.txt` (configurable) |
| `summarizer.py` (per-dir) | all `_sum.txt` in dir | `<dirname>_sum.txt` |
| `formatter.py` | any `*.txt` output above | `*.txt` / `*.md` / `*.html` (per config) |

The Formatter is a no-op when `formatter.format: txt`. For `md` and `html` it reads each `.txt` file, writes the converted file, and removes the `.txt` original.

### `config.py`

Loads and validates `config.yaml`. Exposes a single `Config` dataclass used throughout the app. See [config.yaml](../../config.yaml).

Key sub-configs:

| Dataclass | Purpose |
|---|---|
| `TranscriptionConfig` | whisper-asr-webservice connection and ASR options |
| `OllamaStepConfig` | Ollama connection, model, prompt, and suffix — shared by postprocessing, file_summarization, dir_summarization |
| `FormatterConfig` | Output format (`txt`/`html`/`md`), `enabled` flag, speaker label style |
| `CleanupConfig` | Which output suffixes `--cleanup` removes |
| `ScheduleConfig` | Cron or interval schedule |
| `LoggingConfig` | App log file, request logging, diarization JSON sidecar |

### `scheduler.py`

Wraps the main pipeline run in a cron-style schedule (APScheduler). Also supports one-shot invocation via `--once` CLI flag.

### `main.py`

CLI entry point. Parses args, loads config, starts scheduler or runs once. Houses `output_path()` (path construction for cleanup) and `run_cleanup()`.

## File Output Conventions

- Output files sit **beside** the source audio/video file.
- All pipeline steps always write plain `.txt` regardless of the configured format.
- After each file's steps complete, `Formatter.format_file()` converts each output to the final format (`.md` or `.html`) and removes the `.txt` original.
- A file is only written on **success** — partial/error state writes `_err.txt` (always `.txt`, never converted).
- Language is inferred from filename suffix `_ru`/`_en`/`_auto`; falls back to config default.

### Output format (`formatter.format`)

| Value | Extension | Notes |
| --- | --- | --- |
| `txt` (default) | `.txt` | Formatter is a no-op |
| `html` | `.html` | Content HTML-escaped; diarized output uses `<p>` + `<strong>`/`<em>` tags |
| `md` | `.md` | Diarized speaker labels styled per `speaker_style` and `text_placement` |

### Speaker label rendering (`html` and `md` only)

When diarized transcription produces `[SPEAKER_XX]: text` lines, the Formatter applies visual styling controlled by two config fields under `formatter:`:

- `speaker_style: bold | italic | plain` — emphasis on the `[SPEAKER_XX]:` label (default `bold`)
- `text_placement: same_line | new_line` — whether transcript text follows the label on the same line or starts on the next line (default `same_line`)

Non-diarized files (no `[SPEAKER_XX]:` lines) are converted without modification to their content.

## Error Handling Strategy

Each pipeline step catches its own exceptions and writes `<source>_err.txt` with the error detail. The pipeline continues to the next file — a single failure does not halt the run. After successful completion of all steps for a file, any pre-existing `_err.txt` for that file is removed.
