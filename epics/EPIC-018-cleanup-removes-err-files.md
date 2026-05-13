# EPIC-018: --cleanup Also Removes _err.txt Files

**Status**: Done

## Goal

Extend the `--cleanup` command so that it also deletes `_err.txt` error marker files, in addition to the pipeline output files it already removes.

## Scope

- `src/fileswhisper/main.py` — extend `run_cleanup()` (or equivalent) to include `_err.txt` in the set of deleted files
- The removal should apply to all `_err.txt` files found recursively under `watch_dir`, not just those beside a matching media file
- Respects `--dry-run`: logs what would be deleted without touching the filesystem
- No changes to config schema required — `_err.txt` is always included in cleanup regardless of `cleanup.targets`

## Acceptance Criteria

- [x] `--cleanup` deletes all `_err.txt` files found recursively under `watch_dir`
- [x] `--cleanup --dry-run` logs the `_err.txt` files that would be deleted without removing anything
- [x] Existing behaviour for other output suffixes is unchanged
- [x] If no `_err.txt` files are present, the command exits cleanly with no error

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
