# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**whispercrawl** is a Python service that recursively processes audio/video files in a directory, performing:

1. Transcription + diarization via `whisper-asr-webservice`
2. Post-processing (regex cleanup + LLM correction) via `ollama`
3. Per-file summarization via `ollama`
4. Per-directory summarization via `ollama`

The service runs on a schedule and is config-file driven.

## Commands

```bash
# Install (editable + dev deps)
pip install -e ".[dev]"

# Run once (no schedule)
whispercrawl --config config.yaml --once

# Dry run (log files that would be processed, no API calls)
whispercrawl --config config.yaml --once --dry-run

# Run tests
pytest

# Run a single test file
pytest tests/test_file_walker.py

# Lint + format
ruff check src tests
ruff format src tests

# Start dev stack (two ASR engines: whisper :9000 + whisper2 :9001, ollama :11434;
# gemma3:1b is pulled automatically on first start). The stack mounts
# deploy/dev/config.yaml — the dev config, which pre-wires both engines (EPIC-054).
docker compose -f deploy/dev/docker-compose.dev.yml --env-file deploy/dev/.env up -d

# Rebuild whispercrawl image after changing src/ or pyproject.toml
docker compose -f deploy/dev/docker-compose.dev.yml --env-file deploy/dev/.env up -d --build whispercrawl

# ASR services only (for running whispercrawl locally via python); deploy/dev/app-python*.sh wrap this
docker compose -f deploy/dev/docker-compose.services.yml --env-file deploy/dev/.env up -d
```

## Architecture

### Source layout

```text
src/whispercrawl/
  config.py          # Config dataclass + YAML loader
  file_walker.py     # Recursive file discovery, language detection from filename
  main.py            # CLI entry point (argparse)
  scheduler.py       # APScheduler wrapper (cron/interval)
  pipeline/
    transcriber.py   # POST to whisper-asr-webservice /asr
    postprocessor.py # Regex pass + ollama /api/chat (fix prompt)
    summarizer.py    # ollama /api/chat — per-file and per-directory
```

### Processing Pipeline (per file)

```text
audio/video file
  → Transcriber      → transcript text        (→ index asr_results)
  → PostProcessor    → fixed text             (→ index asr_results, in memory)
  → Summarizer       → summary                (in memory)
  → Composer         → summary + transcript sections
  → Formatter        → <file>.<ext>           (ONE result beside the audio)

after all files in a directory:
  → Summarizer + Composer + Formatter → _<dirname>.<ext>   (dir summary + concat)
```

Each step is independent and skippable. On any step's failure nothing is written
beside the audio (no partial result); the failure is recorded in the processing
index (`status='error'` + an `errors` row per failing step/engine) and processing
continues with the next file. `whispercrawl --errors` lists them. No `_err.txt`
sidecar is ever written (EPIC-051/052).

### Key Conventions

- **One consolidated result** per audio file (`<file>.<ext>`) and per directory
  (`_<dirname>.<ext>`, or `<dirname>.<ext>` when `dir_summarization.underscore_prefix: false`).
  The raw ASR transcript and intermediate post-processed text live in the
  processing index, not beside the audio. The `result:` config section controls
  section order/headings (`file_sections`, `dir_sections`, `*_heading`,
  `heading_level`, `separator`, `include_missing_headings`). Failures are recorded
  in the index, not on disk (EPIC-049) — no sidecars, ever.
- `postprocessing.replace_transcription`, `file_summarization.output_suffix`,
  `dir_summarization.concat_suffix` / `output_suffix` (EPIC-047),
  `state.enabled` / `state.store_text` (EPIC-051), `cleanup.targets` and every
  `*.error_suffix` (EPIC-052), and the whole `cleanup:` section (EPIC-053) are
  **deprecated no-ops** — config load logs a WARNING and ignores them.
  `--cleanup` (alone, or with `--once`) removes only the consolidated result
  files this version writes (`<file>.<ext>` / `_<dirname>.<ext>`, per engine,
  any extension) and empties the index — it is not configurable; with
  `--once --cleanup` a file's result is removed only after every step for it
  succeeded. Pre-047 `_fix` / `_sum` / `_all` / `_concat` files and `_err.txt`
  leftovers are an operator concern (delete by hand when upgrading an old
  catalog).
- Output files sit **beside** the source audio/video file.
- A result is only written on **success** of every step for that file.
- **Language detection**: filename suffix `_ru`, `_en`, or `_auto` overrides the config default language passed to whisper.
- **Skip mode** (`rescan: false`): if `<file>.<ext>` already exists (any format), that file is skipped entirely.
- **Persisted index** (`<config dir>/db/state.db`, SQLite, always on — EPIC-051): a dedicated `db/` directory beside `config.yaml` (`/db/state.db` in the container, its own bind mount). Records `done`/`error` per file so runs skip the per-file output-existence probing and resume after interruption. Safe to delete — rebuilt from existing output files, no reprocessing. A legacy `<watch_dir>/.whispercrawl/state.db` is moved here automatically on first run. Only `state.path` is configurable (override the default location). `max_files_per_run` caps files per run; the rest wait for the next scheduled run.
- **Recorded errors** (EPIC-049): a failing step writes an `errors` row (`path`, `engine`, `scope` `file`/`dir`, `step`, message) — never a `<file>_err.txt` sidecar; the row is cleared when that file/dir next succeeds, and dropped when the source file changes. `whispercrawl --errors` prints outstanding failures grouped by path and exits non-zero if any exist. `--cleanup` empties the `errors` table (with the rest of the index).
- **Per-step resume**: the index also records which pipeline step (transcribe/postprocess/file-summarize) last completed for each file's current mtime/size. An interrupted run resumes mid-file — already-written step outputs are read back from disk instead of re-calling whisper/ollama — rather than restarting the whole file. A changed file (new mtime/size) discards its recorded steps and reprocesses from scratch.
- **Stored transcript text** (always — EPIC-051): the index keeps each file's raw ASR transcript and post-processed text, keyed to its mtime/size. With EPIC-047 this is the *only* place the raw transcript lives — the on-disk result holds the post-processed (or raw) transcript body, never both. Resume and `--refresh` read the transcript back from here.
- **`--refresh`**: a single pass that re-runs every step downstream of ASR (postprocess → summary → dir concat/summary → compose → format) from the stored transcript with the current config and **no whisper call** — the fast path for iterating on prompts, models, `formatter`, or `result`. Honors `skip_marker` / `max_age_days` / `max_files_per_run` / `processing_mode`; a file with no stored text is skipped (no error recorded); a changed source file is skipped (its stored text is stale). Changing `transcription` settings still requires `rescan: true`.
- **Multiple ASR engines** (`transcription.engines`, EPIC-048): a list of engine configs, each merged onto the top-level `transcription` block (entry values win). Every engine transcribes every file and produces its **own** result files — `<file>_<name>.<ext>` and `_<dirname>_<name>.<ext>` — and its own rows in the processing index (raw/fixed text keyed by engine in the `asr_results` table, `step:<name>` tokens). One engine failing records an `errors` row for that engine and does not block the others; the file is recorded `done` only once every engine finished. `--refresh` regenerates each engine from its stored text; an engine with no stored text for a file is skipped. With no `engines:` list there is one implicit engine (`name: ""`) and output names are unchanged. `max_files_per_run` counts **files**, not file×engine. Engine `name` must match `[A-Za-z0-9._-]+` and be unique.
- **Diarization JSON** (`logging.diarize_log: true`): raw service JSON is written under `<log_dir>/diarize/<path-relative-to-watch_dir>.json` (a debug artifact, not beside the audio and not a pipeline input). With named engines it goes under `<log_dir>/diarize/<engine>/`.
- **Processing mode** (`processing_mode`, default `per_file`): `per_file` runs every step on one file before moving to the next; `per_step` runs each step across all pending files before the next step starts (reduces Ollama model-swap overhead when postprocessing/file_summarization use different models). Both produce identical output — only step ordering differs.

### Config

Edit [config.yaml](config.yaml) directly — it is the working example (single ASR
engine). Key sections: `transcription`, `postprocessing`, `file_summarization`,
`dir_summarization`, `result`, `formatter`, `schedule`.
[deploy/dev/config.yaml](deploy/dev/config.yaml) is the dev copy — same sections,
but with `transcription.engines` pre-wired to two ASR services (`whisperx` :9000,
`faster` :9001); the dev Docker stack and `deploy/dev/app-python*.sh` use it (EPIC-054).

## Planning Files

- [docs/architecture/overview.md](docs/architecture/overview.md) — component diagram and responsibilities
- [docs/architecture/decisions/](docs/architecture/decisions/) — Architecture Decision Records
- [docs/api/](docs/api/) — external API notes (whisper, ollama)
- [epics/](epics/) — one file per feature with goal, scope, and acceptance criteria; named `EPIC-NNN-<slug>.md`
- [tasks/backlog.md](tasks/backlog.md) — granular task checklist; **check this file at the start of any work session and pick up open items**

### Working with epics and tasks

- To add a feature: create an `epics/EPIC-NNN-<slug>.md` file first, then implement when told to.
- To implement: read the epic file for acceptance criteria, then work through the tasks.
- To track progress: mark tasks `[x]` in `tasks/backlog.md` as they complete; move them to `tasks/done.md` when the epic is fully done.
- Backlog is the source of truth for what remains; epics are the source of truth for scope and intent.

## Target Environments

- **Dev/Test**: Windows 11 with Docker + Ollama
- **Production**: RedOS 8 (Linux) with external whisper-asr-webservice and Ollama

The ASR service image is referenced as `asr-webservice:latest` (mirrored from the
upstream `onerahmet/openai-whisper-asr-webservice:latest`). Every compose file
resolves it via `${ASR_IMAGE:-asr-webservice:latest}` — set `ASR_IMAGE` in the
env file to pull from an internal registry instead of loading `whisper.tar`.
