# EPIC-005: Output Cleanup & Service Interaction Logging

**Status**: Done

## Goal

Two independent improvements to the pipeline:

1. **Output cleanup** — a config flag that deletes intermediate and final output files produced by the service after a configurable retention period or immediately after the run, so the watch directory doesn't accumulate stale `.txt` files indefinitely.
2. **Service interaction logging** — structured per-request logging for every call to whisper-asr-webservice and ollama, recording timing, model, file, and response metadata to help diagnose slow or failed runs.

## Scope

### Cleanup (`cleanup` config section)

- New top-level config section `cleanup` with:
  - `enabled: bool` — master switch (default `false`)
  - `targets: list[str]` — which suffixes to remove, e.g. `[".txt", "_fix.txt", "_sum.txt"]`
  - `on: "success" | "always"` — delete only when the full pipeline for a file succeeds, or unconditionally after each run
- Implemented in `pipeline/cleaner.py` as a `Cleaner` class called at the end of `run_pipeline()`
- Config loaded in `config.py` as a new `CleanupConfig` dataclass

### Interaction Logging (`logging` config section)

- New top-level config section `logging` with:
  - `requests: bool` — log each outbound HTTP request to whisper/ollama (default `false`)
  - `log_file: str | null` — path to append structured JSON log lines; `null` means stderr only
- Log entry fields: `timestamp`, `service` (`whisper` | `ollama`), `file`, `model`, `duration_s`, `status_code`, `response_size_bytes`
- Implemented as a thin wrapper / context manager in `utils/service_logger.py`
- Injected into `Transcriber`, `PostProcessor`, and `Summarizer` via their constructors

## Acceptance Criteria

- [x] With `cleanup.enabled: true` and `cleanup.on: "success"`, output files for a fully processed audio file are removed after the run
- [x] With `cleanup.on: "always"`, output files are removed even when a pipeline step failed
- [x] `cleanup.targets` controls which suffixes are deleted; suffixes absent from the list are kept
- [x] With `logging.requests: true`, every whisper and ollama call emits a log line with file name, service, model, duration, and HTTP status
- [x] With `logging.log_file` set, log lines are appended to that file in newline-delimited JSON (ndjson)
- [x] With `logging.requests: false` (default), no extra log output is produced — existing behaviour is unchanged
- [x] All new config fields have defaults that preserve the current behaviour when the section is absent from `config.yaml`

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
