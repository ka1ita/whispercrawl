# ADR-005: Record Pipeline Errors in the Index, Not in `_err.txt` Sidecars

**Date**: 2026-09-02
**Status**: Accepted

## Context

Every failing pipeline step wrote a `<file><engine>_err.txt` (or
`_<dirname><engine>_err.txt`) next to the source media, and the next success
deleted it (EPIC-016 / EPIC-018). EPIC-047 moved every *successful* artifact off
the audio tree — the transcript into the index, one consolidated result per file
— but the error case still littered it. The message also lived only on disk:
over a large catalog the only way to see "what failed and why" was
`grep -r _err.txt`. The index already recorded `files.status = 'error'`, but with
a one-line summary `detail`, not the exception text, and with no per-step or
per-engine granularity — and a directory-summary failure has no `files` row at
all.

## Decision

A failing step records a row in a new `errors` table instead of writing a
sidecar. `whispercrawl --errors` reads them back.

- **Schema** (`state.py`, v5): `errors(path, engine, scope, step, message,
  mtime, size, updated_at)`, primary key `(path, engine, scope, step)`. `scope`
  is `file` or `dir`; a `dir` row keys `path` to a directory (relative to
  `watch_dir`) with `mtime` / `size` NULL. The table is created by
  `CREATE TABLE IF NOT EXISTS` in the schema script — a v4 DB gains it on open
  with no data migration (pre-049 errors were on disk; `--cleanup` sweeps them).
- **`record_error` / `clear_errors` / `get_errors`** on `ProcessingState`
  (no-ops / `[]` on `NullState`). `clear_errors(engine=None)` clears every
  engine for a path/scope, `clear_errors(engine=<name>)` one — used so a
  succeeding engine does not wipe a sibling engine's fresh failure.
- **`main.py`**: a `_report_error` helper writes an `errors` row when the index
  is a live `ProcessingState`, else falls back to the `_err.txt` sidecar. The
  three per-file steps and the per-directory loop call it; `_finalize_one` /
  the dir loop call `clear_errors` for that engine on success. `mark_step`'s
  existing `mtime`/`size`-mismatch reset also `DELETE`s the file's `errors`
  rows, so a new generation of a changed file starts clean — the same rule
  already applied to `asr_results`.
- **`--errors`** opens the index read-only, prints outstanding rows grouped by
  path (`[engine] step   first line of message`), and exits non-zero when any
  exist so a cron wrapper can alert; exits zero on a clean index or a disabled
  one (with a note).
- **`state.enabled: false`** keeps the `<file><engine>_err.txt` sidecar exactly
  as before — the index is the only place errors can go, so with no index the
  fallback must stay or a failure is lost. The `error_suffix` config fields
  remain for this path and for `--cleanup`'s legacy sweep.

## Alternatives considered

- **Widen `files.detail` to hold the full message.** Rejected — no per-step /
  per-engine granularity, and directory-summary failures have no `files` row.
- **Drop the sidecar entirely, even when the index is disabled.** Rejected — a
  disabled index plus no sidecar means a silent failure. The fallback is cheap.
- **A machine-readable `--errors --json`.** Deferred — the first cut is
  human-readable plus an exit code; a wrapper that needs JSON can get it later.
- **Migrating existing `_err.txt` contents into the table on upgrade.**
  Rejected — they are swept by `--cleanup`; a still-failing file re-creates the
  row on the next run.

## Consequences

- The audio tree stays clean through failures, not only successes.
- `whispercrawl --errors` is the one place to triage a run; its exit code drives
  alerting.
- One more schema bump (v4 → v5); a v4 DB upgrades in place and `state.db`
  remains safe to delete (rebuilt from output files; outstanding errors are
  simply re-discovered on the next run).
- `_finalize_file`'s stale-sidecar sweep now runs only under the disabled-index
  fallback; `run_cleanup`'s `*_err.txt` sweep is legacy-only.
- Tests that asserted `_err.txt` existence now assert an `errors` row via
  `ProcessingState.get_errors`.
