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

Persisted index of processed files, backed by a single SQLite file at `<config dir>/db/state.db` — a dedicated `db/` directory beside `config.yaml` (`/db/state.db` in the container, backed by its own bind mount). Always on (EPIC-051); the only knob is `state.path`, which overrides the default location. Each run records `done` / `error` per file so subsequent runs answer "already processed?" with an indexed lookup instead of up to three `exists()` probes per file, and an interrupted run resumes without redoing completed work. A file absent from the index but already carrying an output file is recorded as `done` on first sight — so enabling the index on an existing catalog reprocesses nothing. **Deleting `state.db` is safe**: the next run rebuilds it from whichever output files exist.

An index left at the pre-EPIC-043 location (`<watch_dir>/.whispercrawl/state.db`) is moved to the new `db/` directory automatically on the first run — a one-time, best-effort migration (including the SQLite `-wal`/`-shm` sidecars); if it fails the run just starts a fresh index. `file_walker` never descends into a `db/` or `.whispercrawl/` directory under `watch_dir`.

`max_files_per_run` caps how many files a single run processes; the remainder are picked up on the next scheduled run (safe because progress is persisted).

**Per-step resume.** Alongside the overall `done`/`error`/`partial` status, each file's row also tracks which individual pipeline step last completed (`transcribe`, `postprocess`, `file_summarize`) for its current `mtime`/`size`. If a run is interrupted mid-file — a crash, a `max_files_per_run` cutoff, `Ctrl-C` — the next run reads the already-written output of each completed step back from disk instead of re-calling the ASR/LLM services, and only resumes the steps that didn't finish. A row whose `mtime`/`size` no longer match the file on disk (it changed since the last attempt) discards its recorded steps and reprocesses from scratch. A file with a recorded `error`/`partial` row is always re-queued for another attempt, even if an earlier step's output already exists on disk — it is never silently treated as fully `done` just because one output file happens to be present.

**Stored transcript text and `--refresh`.** The `asr_results` table holds each file's raw ASR transcript and post-processed text — one row per `(path, engine, kind)`, keyed to the file's `mtime`/`size`. This keeps the one slow, non-deterministic output — the ASR result — even after the on-disk result is post-processed over or converted to `.md`/`.html`, and it powers `whispercrawl --refresh`: a single pass that re-runs every step *downstream* of ASR (post-process → per-file summary → per-directory concat/summary → compose → format) from the stored transcript, with the current config and **zero** whisper calls. It is the fast path for iterating on the fix prompt, the summary model, the `result:` section, or the output format. `--refresh` visits every media file that passes the `skip_marker` / `max_age_days` / `max_files_per_run` traversal filters (the index skip is bypassed) and honors `processing_mode`; per engine, a file with no stored transcript for that engine is logged and skipped (no error recorded). After a successful `--refresh` the file's steps are re-marked complete, so a later normal run skips it. A changed `mtime`/`size` invalidates the stored text (`mark_step`'s reset deletes the file's `asr_results` rows) — a normal run re-transcribes, `--refresh` skips. Changing `transcription` settings (`diarize`, `language`, `speaker_timestamps`, …) still needs a real re-transcribe via `rescan: true`.

**Recorded errors (EPIC-049).** The `errors` table holds one row per failing pipeline step — `(path, engine, scope, step)` where `scope` is `file` or `dir` — with the full exception message. This replaces the `<file>_err.txt` sidecar entirely (EPIC-051 removed the last fallback): a step failure records a row and leaves nothing beside the audio, the row is cleared when that file / directory next succeeds, and `mark_step`'s `mtime`/`size` reset drops it along with the stale `asr_results` rows. `whispercrawl --errors` prints the outstanding rows grouped by path and exits non-zero when any exist.

Every run has at least one ASR engine (`config.transcription.engines`, always a non-empty list — a lone `transcription:` block becomes the single engine with `name == ""`). Multiple engines get their own `asr_results` rows and `step:<engine>` tokens; see [EPIC-048](../../epics/EPIC-048-multiple-asr-engines.md). The dev stack ships this configured: `deploy/dev/docker-compose.dev.yml` runs two `whisper-asr-webservice` containers — `whisper` on host port 9000 and `whisper2` on 9001 — and mounts `deploy/dev/config.yaml`, whose `engines:` list points at both ([EPIC-054](../../epics/EPIC-054-dev-second-asr-engine.md)).

**Concurrent transcription (EPIC-056).** `transcription.concurrency` (int, default `1`) bounds how many engines' `/asr` calls are in flight at once. Only the transcribe step is parallelised — a short-lived `ThreadPoolExecutor` runs the blocking HTTP calls; the worker returns a plain result and the main thread applies every `asr_results` / `errors` / status write, so the SQLite index is never touched off the main thread. Post-processing, summarization, and the per-directory pass stay sequential (Ollama serves one model at a time). `concurrency: 1`, a single engine, or `--refresh` takes the sequential path with no pool. In `per_file` mode a file's engines overlap; in `per_step` mode one pool bounds all `(file, engine)` `/asr` calls across the transcribe phase. Output is identical to a sequential run — only wall-clock differs. See [ADR-010](decisions/ADR-010-concurrent-transcription.md).

### Processing mode (`processing_mode`)

Controls the order the per-file pipeline steps run in across a batch:

- `per_file` (default): every step (transcribe → postprocess → file-summarize) runs on one file before moving to the next file.
- `per_step`: each step runs across **all** pending files before the next step starts — transcribe every file, then postprocess every survivor, then file-summarize every survivor. Useful when `postprocessing` and `file_summarization` point at different Ollama models, since the model only needs to be loaded once per step instead of being swapped on nearly every file.

Both modes write identical output — same files, same content, same `state.db` step-tracking (see [EPIC-041](../../epics/EPIC-041-per-step-resume.md)) — only the order of work differs. A transcription failure excludes a file from later steps in either mode; a postprocessing failure does not exclude a file from summarization (it falls back to the original transcript, per `summarize_source`).

### `pipeline/`

Since EPIC-047 each processed file and each processed directory produces **one**
consolidated result. The raw ASR transcript and the intermediate post-processed
text are held in the processing index (`state.py`), not written beside the audio.

| Module | Input | Output |
|---|---|---|
| `transcriber.py` | audio/video path | transcript text (→ index `asr_results`) |
| `postprocessor.py` | transcript text | fixed text (→ index `asr_results`, in memory) |
| `summarizer.py` (per-file) | transcript / fixed text | summary text (in memory) |
| `summarizer.py` (per-dir) | all transcripts in the dir | concat + optional dir summary (in memory) |
| `composer.py` | `(summary, transcript)` sections | one plain-text document with `#` headings |
| `formatter.py` | the composed `.txt` | `<file>.txt` / `.md` / `.html`, `_<dirname>.<ext>` |

`composer.compose(sections, bodies, headings, ResultConfig)` joins the ordered
sections as `# heading` + body blocks (`result.separator` between them). A single
surviving section is emitted bare (no heading) unless
`result.include_missing_headings` is set. The Formatter recognises those `#`
headings and `---` rules: `md`/`txt` pass them through, `html` renders `<h1>…`/`<hr>`.

The Formatter is a no-op when `formatter.format: txt`. For `md` and `html` it
reads the composed `.txt`, writes the converted file, and removes the `.txt`.

Per-file result: `<file>.<ext>` — `result.file_sections` (summary then transcript
body; the body is the post-processed text when post-processing ran, else the raw
transcript). Per-directory result: `_<dirname>.<ext>` (or `<dirname>.<ext>` when
`dir_summarization.underscore_prefix: false`) — `result.dir_sections` (dir summary
then every transcript concatenated with filename headers). Failures are recorded
in the processing index (`errors` table), never written beside the audio.

### `config.py`

Loads and validates `config.yaml`. Exposes a single `Config` dataclass used throughout the app. See [config.yaml](../../config.yaml).

Key sub-configs:

| Dataclass | Purpose |
|---|---|
| `TranscriptionConfig` | whisper-asr-webservice connection and ASR options; `name` + `engines` list for multi-engine (EPIC-048); `concurrency` bounds parallel `/asr` calls (EPIC-056) |
| `OllamaStepConfig` | Ollama connection, model, prompt — shared by postprocessing, file_summarization, dir_summarization |
| `FormatterConfig` | Output format (`txt`/`html`/`md`), `enabled` flag, speaker label style |
| `ResultConfig` | Consolidated-result assembly: section order/headings, heading level, separator (`result:`) |
| `ScheduleConfig` | Cron or interval schedule |
| `StateConfig` | Processing-index location (`path`) — the index is always on and always stores transcript text (EPIC-051) |
| `LoggingConfig` | App log file, request logging, diarization JSON dump (`<log_dir>/diarize/`) |

### `scheduler.py`

Wraps the main pipeline run in a cron-style schedule (APScheduler). Also supports one-shot invocation via `--once` CLI flag.

### `main.py`

CLI entry point. Parses args, loads config, starts scheduler or runs once. Houses `output_path()` (path construction for cleanup) and `run_cleanup()`.

CLI flags: `--once` (single run, no schedule), `--dry-run` (log what would be processed), `--cleanup` (delete the current-version consolidated results and empty the processing index; not configurable — optionally combined with `--once`, where a file's result is removed only after every step for it succeeded), `--errors` (list failures recorded in the index; exits non-zero if any are outstanding), `--refresh` (single downstream-only pass from stored transcript text — see `state.py` above). Branch order in `main()`: `--cleanup` → `--errors` → `--refresh` → `--once`/`--dry-run` → scheduler.

## File Output Conventions

- Output files sit **beside** the source audio/video file.
- One consolidated result per audio file (`<file>.<ext>`) and one per directory (`_<dirname>.<ext>`); no `_fix`/`_sum`/`_all`/`_concat` sidecars (EPIC-047).
- The composed result is assembled as plain `.txt`, then `Formatter.format_file()` converts it to `.md`/`.html` and removes the `.txt`.
- A result is written only on **success** of every step for that file — otherwise the failure is recorded in the index `errors` table and cleared on the next success.
- **Any** exception in a step is contained (EPIC-055): the typed pipeline error *and* anything unexpected (source file vanished before transcription, permission error, disk full on the write, malformed service body) is logged, written as an `errors` row (`step` may be `finalize` / `format` / `dir_finalize`), and the run continues with the next file. Only `KeyboardInterrupt` / `SystemExit` abort it (`status='partial'`).
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

Each pipeline step catches its own exceptions and records the failure in the processing index: `files.status = 'error'` plus an `errors` row per failing step and engine (`scope` `file` or `dir`, the full message). The pipeline continues to the next file — a single failure does not halt the run, and one engine failing does not block the others. The row is cleared when that file / directory next completes successfully, and dropped when the source file changes (mtime/size). `whispercrawl --errors` prints the outstanding rows grouped by path and exits non-zero when any exist; `whispercrawl --cleanup` empties the table with the rest of the index. Nothing is ever written beside the audio on failure — no `_err.txt` sidecar in any configuration (EPIC-051/052).
