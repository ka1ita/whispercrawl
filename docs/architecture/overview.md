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

Files are yielded **newest first** (by mtime). `max_age_days` bounds the scan to a recent window. When the persisted index (`state.py`) is enabled, files recorded as `done` with an unchanged mtime/size are skipped without probing the filesystem for output files.

### `state.py`

Persisted index of processed files, backed by a single SQLite file at `<config dir>/db/state.db` — a dedicated `db/` directory beside `config.yaml` (`/db/state.db` in the container, backed by its own bind mount). Overridable via `state.path`; disable entirely with `state.enabled: false`. Each run records `done` / `error` per file so subsequent runs answer "already processed?" with an indexed lookup instead of up to three `exists()` probes per file, and an interrupted run resumes without redoing completed work. A file absent from the index but already carrying an output file is recorded as `done` on first sight — so enabling the index on an existing catalog reprocesses nothing. **Deleting `state.db` is safe**: the next run rebuilds it from whichever output files exist.

An index left at the pre-EPIC-043 location (`<watch_dir>/.whispercrawl/state.db`) is moved to the new `db/` directory automatically on the first run — a one-time, best-effort migration (including the SQLite `-wal`/`-shm` sidecars); if it fails the run just starts a fresh index. `file_walker` never descends into a `db/` or `.whispercrawl/` directory under `watch_dir`.

`max_files_per_run` caps how many files a single run processes; the remainder are picked up on the next scheduled run (safe because progress is persisted).

**Per-step resume.** Alongside the overall `done`/`error`/`partial` status, each file's row also tracks which individual pipeline step last completed (`transcribe`, `postprocess`, `file_summarize`) for its current `mtime`/`size`. If a run is interrupted mid-file — a crash, a `max_files_per_run` cutoff, `Ctrl-C` — the next run reads the already-written output of each completed step back from disk instead of re-calling the ASR/LLM services, and only resumes the steps that didn't finish. A row whose `mtime`/`size` no longer match the file on disk (it changed since the last attempt) discards its recorded steps and reprocesses from scratch. A file with a recorded `error`/`partial` row is always re-queued for another attempt, even if an earlier step's output already exists on disk — it is never silently treated as fully `done` just because one output file happens to be present.

### Processing mode (`processing_mode`)

Controls the order the per-file pipeline steps run in across a batch:

- `per_file` (default): every step (transcribe → postprocess → file-summarize) runs on one file before moving to the next file.
- `per_step`: each step runs across **all** pending files before the next step starts — transcribe every file, then postprocess every survivor, then file-summarize every survivor. Useful when `postprocessing` and `file_summarization` point at different Ollama models, since the model only needs to be loaded once per step instead of being swapped on nearly every file.

Both modes write identical output — same files, same content, same `state.db` step-tracking (see [EPIC-041](../../epics/EPIC-041-per-step-resume.md)) — only the order of work differs. A transcription failure excludes a file from later steps in either mode; a postprocessing failure does not exclude a file from summarization (it falls back to the original transcript, per `summarize_source`).

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
| `StateConfig` | Persisted processing-index toggle and path |
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

When diarized transcription produces speaker lines, the Formatter applies visual styling controlled by two config fields under `formatter:`:

- `speaker_style: bold | italic | plain` — emphasis on the speaker label (default `bold`)
- `text_placement: same_line | new_line` — whether transcript text follows the label on the same line or starts on the next line (default `same_line`)

All three label shapes the transcriber emits are recognised: `[SPEAKER_XX]: text` (`speaker_timestamps` off), `[SPEAKER_XX HH:MM:SS] text`, and `[SPEAKER_XX] text` (`speaker_timestamps` on). The trailing colon is reproduced only when the source line had one — the timestamped form renders as `**[SPEAKER_XX HH:MM:SS]**` with no colon.

Non-diarized files (no `[SPEAKER_XX …]` lines) are converted without modification to their content.

## Error Handling Strategy

Each pipeline step catches its own exceptions and writes `<source>_err.txt` with the error detail. The pipeline continues to the next file — a single failure does not halt the run. After successful completion of all steps for a file, any pre-existing `_err.txt` for that file is removed.
