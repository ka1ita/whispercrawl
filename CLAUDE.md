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

# Start dev services (whisper + ollama via Docker; gemma3:1b is pulled automatically on first start)
docker compose -f deploy/dev/docker-compose.dev.yml --env-file deploy/dev/.env up -d

# Rebuild whispercrawl image after changing src/ or pyproject.toml
docker compose -f deploy/dev/docker-compose.dev.yml --env-file deploy/dev/.env up -d --build whispercrawl
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
  → Transcriber      → <file>.txt
  → PostProcessor    → <file>_fix.txt
  → Summarizer       → <file>_sum.txt

after all files in a directory:
  → Summarizer       → <dirname>_sum.txt
```

Each step is independent and skippable. On error, `<file>_err.txt` is written and processing continues with the next file.

### Key Conventions

- Output files sit **beside** the source audio/video file.
- A file is only written on **success**. On error, `_err.txt` is written instead.
- **Language detection**: filename suffix `_ru`, `_en`, or `_auto` overrides the config default language passed to whisper.
- **Skip mode** (`rescan: false`): if `<file>.txt` already exists, that file is skipped entirely.

### Config

Edit [config.yaml](config.yaml) directly — it is the working example. Key sections: `transcription`, `postprocessing`, `file_summarization`, `dir_summarization`, `schedule`.

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
