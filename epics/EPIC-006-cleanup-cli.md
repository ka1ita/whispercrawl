# EPIC-006: --cleanup CLI Flag

**Status**: Done

## Goal

Add a `--cleanup` flag to the CLI that deletes all pipeline output files in `watch_dir` without running transcription, post-processing, or summarization. Mirrors the `--once` pattern: one-shot, then exit.

## Scope

- `src/fileswhisper/main.py` — new `--cleanup` argument + `run_cleanup()` function
- Uses `cleanup.targets` from config to know which suffixes to remove (falls back to defaults if the `cleanup` section is absent)
- Respects `--dry-run`: logs what would be deleted without touching the filesystem
- Scans recursively under `watch_dir`, same extension list as the normal pipeline
- Also removes per-directory summary files (`<dirname>_sum.txt`) found beside the media files
- No calls to whisper or ollama

## CLI Interface

```
fileswhisper --config config.yaml --cleanup            # delete outputs
fileswhisper --config config.yaml --cleanup --dry-run  # preview only
```

## Acceptance Criteria

- [x] `--cleanup` deletes every output file whose suffix is in `cleanup.targets` beside a matching media file
- [x] `--cleanup --dry-run` logs files that would be deleted without removing anything
- [x] Directory summary files (`<dirname>_sum.txt`) are also removed
- [x] No whisper or ollama calls are made when `--cleanup` is used
- [x] If no output files are found, the command exits cleanly with an info log

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
