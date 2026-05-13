# EPIC-016: Remove _err.txt After Successful Processing

**Status**: Planned

## Goal

When a file is successfully processed, delete any `_err.txt` file left behind
by a previous failed run. This prevents stale error files from cluttering the
output directory and causing confusion about the current state of a file.

## Background

On failure the pipeline writes `<file>_err.txt` and moves on. On the next run
(or after a config/service fix), the same file may succeed — but the old
`_err.txt` remains alongside the new `.txt` output, making it look like the
file is still in an error state.

## Scope

### What triggers cleanup

After each pipeline step succeeds and writes its output file, remove the
corresponding `_err.txt` if it exists:

| Output written         | Error file to remove     |
|------------------------|--------------------------|
| `<file>.txt`           | `<file>_err.txt`         |
| `<file>_fix.txt`       | `<file>_err.txt`         |
| `<file>_sum.txt`       | `<file>_err.txt`         |
| `<dirname>_sum.txt`    | `<dirname>_err.txt`      |

A single `_err.txt` per source file covers all pipeline steps (the current
convention). Cleanup happens at the end of successful full-file processing, not
per-step, to avoid removing the error file prematurely if a later step fails.

### What is NOT in scope

- Removing `_err.txt` files for files that are skipped (not reprocessed).
- Any new config flags — cleanup is unconditional and always on.

## Files to Change

- `src/fileswhisper/pipeline/transcriber.py` — expose helper or return path for cleanup
- `src/fileswhisper/file_walker.py` or the top-level pipeline orchestrator — delete `_err.txt` after full success
- `tests/` — cover the cleanup behaviour

## Acceptance Criteria

- [ ] After a file completes the full pipeline successfully, its `_err.txt` is
  deleted if it exists
- [ ] If no `_err.txt` exists, processing is unaffected (no error, no log noise)
- [ ] If a later pipeline step fails, `_err.txt` is **not** deleted (the error
  file is updated/preserved for that failure)
- [ ] Directory-level `_err.txt` is removed after a successful directory summary
- [ ] Tests cover: success with pre-existing `_err.txt` (file deleted); success
  with no `_err.txt` (no-op); partial failure (file preserved)

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
