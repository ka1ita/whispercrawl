# EPIC-049: Record Pipeline Errors in the Index, Not in `_err.txt` Sidecars

## Goal

A failed step should leave **nothing beside the audio**. Today a step failure
writes `<file><engine>_err.txt` (and `_<dirname><engine>_err.txt` for a
directory) next to the source media; the next success deletes it again
([[EPIC-016]], [[EPIC-018]]). After this epic the failure — its step, its
engine, and the exception message — is written to the **processing index**
instead, and `_err.txt` files are gone from the normal pipeline.

The index already records `files.status = 'error'` with a one-line `detail`
([[EPIC-040]]); this epic keeps the full message, per engine and per step, and
adds a way to read it back (`whispercrawl --errors`).

With `state.enabled: false` there is no index to write to, so the `_err.txt`
sidecar stays as the fallback in that one configuration (documented).

## Problem Description

`_write_error()` ([main.py:49](../src/whispercrawl/main.py#L49)) writes a
sidecar for every failing step:

- `_transcribe_engine` → `<stem><elabel><transcription.error_suffix>.txt`
  ([main.py:310](../src/whispercrawl/main.py#L310))
- `_postprocess_one` → `<stem><elabel><postprocessing.error_suffix>.txt`
  ([main.py:357](../src/whispercrawl/main.py#L357))
- `_summarize_one` → `<stem><elabel><file_summarization.error_suffix>.txt`
  ([main.py:384](../src/whispercrawl/main.py#L384))
- the per-directory loop → `<prefix><dirname><elabel><dir_summarization.error_suffix>.txt`
  ([main.py:498](../src/whispercrawl/main.py#L498))

`_finalize_file` and the dir loop then `unlink()` a stale err file on the next
success ([main.py:430](../src/whispercrawl/main.py#L430),
[main.py:494](../src/whispercrawl/main.py#L494)), and `run_cleanup` sweeps every
`*<error_suffix>.txt` under `watch_dir`
([main.py:112](../src/whispercrawl/main.py#L112)).

Consequences:

- The audio tree is never actually clean while anything is failing — the exact
  thing [[EPIC-047]] set out to fix for the success case is still true for the
  error case.
- The error message lives only on disk. A run over a large catalog gives no
  single place to see "what failed and why" — you `grep -r _err.txt`.
- The index says `status = 'error'` but `detail` is a summary
  (`"pipeline step failed for engine(s): faster"`), not the exception text.
- `_err.txt` is a second source of truth: delete the index and the next run
  re-derives `done` from output files, but the `_err.txt` files are orphaned
  until `--cleanup`.

## Scope

### 1. `state.py` — an `errors` table

- Bump `SCHEMA_VERSION` to `"5"`.
- New table (same shape discipline as `asr_results`):
  ```sql
  CREATE TABLE IF NOT EXISTS errors (
      path    TEXT NOT NULL,
      engine  TEXT NOT NULL,          -- '' = single implicit engine
      scope   TEXT NOT NULL,          -- 'file' | 'dir'
      step    TEXT NOT NULL,          -- 'transcribe' | 'postprocess' | 'file_summarize' | 'dir_summarize'
      message TEXT NOT NULL,
      mtime   REAL,                   -- source file mtime/size at failure time
      size    INTEGER,                -- NULL for scope='dir'
      updated_at REAL NOT NULL,
      PRIMARY KEY (path, engine, scope, step)
  );
  ```
  For `scope = 'dir'`, `path` is the directory path relative to `watch_dir`
  and `mtime` / `size` are `NULL`.
- Migration is table-create only (`CREATE TABLE IF NOT EXISTS` in `_SCHEMA`,
  same as `asr_results`); no data to move — pre-049 errors live in `_err.txt`
  files a `--cleanup` still sweeps (see §4). Bump the `schema_version` meta row.
- New methods on `ProcessingState`:
  - `record_error(rel_path, step, message, *, engine="", scope="file", mtime=None, size=None) -> None`
    — upsert one row.
  - `clear_errors(rel_path, *, engine=None, scope="file") -> None` — delete this
    path's error rows; `engine=None` clears every engine, a value clears one.
    Called on a step / file / dir **success**.
  - `get_errors(rel_path=None) -> list[ErrorRecord]` — all outstanding errors,
    or those for one path. Used by `--errors` and the end-of-run summary.
  - `ErrorRecord` dataclass mirroring the columns.
- `mark_step`'s existing mtime/size-mismatch reset also runs
  `DELETE FROM errors WHERE path = ?` (a new generation of the file starts with
  a clean slate, same rule already applied to `asr_results`).
- `forget(rel)` and `clear()` also clear `errors`.
- `NullState`: `record_error` / `clear_errors` no-ops, `get_errors` → `[]`.

### 2. `main.py` — write failures to the index

- Replace every `_write_error(file_path, …, str(e))` call with
  `state.record_error(rel, step, str(e), engine=eng, scope="file", mtime=…, size=…)`
  plus the existing `logger.error(...)`.
- Keep `_write_error` **only** as the `state.enabled: false` fallback: a tiny
  `_report_error(ctx_or_dir, step, message)` helper writes to the index when
  `state` is a `ProcessingState`, else falls back to the `_err.txt` sidecar
  with the configured `error_suffix`. (`NullState` is the disabled case;
  `--dry-run` also uses `NullState` but never reaches a write.)
- On success:
  - `_postprocess_one` / `_summarize_one` (per step) and `_finalize_one`
    call `state.clear_errors(rel, engine=eng, scope="file")` — replacing the
    stale-`_err.txt`-`unlink()` in `_finalize_file` (that block goes away, along
    with its `output_path(... error_suffix ...)` probing).
  - the per-directory loop calls `state.clear_errors(dir_rel, scope="dir")` on a
    successful compose+write, and `state.record_error(dir_rel, "dir_summarize",
    str(e), engine=eng, scope="dir")` on `SummarizationError` — the
    `dir_err_path.write_text` / `unlink` pair goes away.
- End of `_run_pipeline`: if `state.get_errors()` is non-empty, log a single
  `WARNING` — `"N file(s) / M directory step(s) finished with errors; "
  "run 'whispercrawl --errors' for details"`.
- `_finalize_file`: `status` / `detail` logic unchanged (`detail` still the
  short engine list); the full messages are now queryable rows.

### 3. `main.py` — `--errors` command

- New `--errors` argparse flag. Branch order:
  `--cleanup` → `--errors` → `--refresh` → `--once` / `--dry-run` → scheduler.
- Opens the index read-only (`open_state`, no migration side effects beyond the
  v5 create), prints each outstanding error grouped by path:
  ```
  audio/stalin2/Сообщение № 10.mp3
    [faster] transcribe   HTTP 504 from http://localhost:9001/asr
  audio/stalin2  (directory)
    [whisperx] dir_summarize   ollama: model 'gemma3:1b' not found
  ```
  Exit non-zero when there is at least one error row (so a cron wrapper can
  alert), zero when the index is clean.
- `state.enabled: false` → print a note that error tracking is disabled and
  errors are in `*<error_suffix>.txt` files; exit zero.

### 4. Cleanup & config

- `run_cleanup`: keep the `*<error_suffix>.txt` recursive sweep — it now only
  removes **legacy** (pre-049) sidecars, same role as the `_fix` / `_sum`
  legacy sweep. Add a one-line comment saying so.
- `pipeline/cleaner.py`: `Cleaner.clean` already skips err suffixes (they are
  not in `cleanup.targets`); no change.
- `config.py`: the four `error_suffix` fields stay (used by the disabled-state
  fallback and the legacy sweep). Add a comment in each config file that
  `error_suffix` only applies when `state.enabled: false`; on the default
  (index enabled) path, failures are recorded in `db/state.db` and read with
  `whispercrawl --errors`.
- `file_walker.py`: no change — `_err.txt` was never counted as an output for
  the back-fill / skip check, and a file with an `error` row is already
  re-queued ([file_walker.py:81](../src/whispercrawl/file_walker.py#L81)).

### 5. Docs

- `CLAUDE.md` Key Conventions: replace "`_err.txt` is the only remaining
  sidecar and only on failure" with: failures are recorded in the processing
  index (`status='error'` + an `errors` row per failing step/engine), surfaced
  by `whispercrawl --errors`; no sidecar is written unless `state.enabled:
  false`. Note the `--errors` command near `--refresh`.
- `docs/architecture/overview.md`: pipeline table — "on any step's failure, an
  `errors` row is written (no partial result, no sidecar)"; document `--errors`.
- `docs/architecture/decisions/`: ADR — index row vs. sidecar for errors;
  the `state.enabled: false` fallback; why `errors` is its own table (dir-scope
  rows have no `files` row, and per-step/per-engine granularity).
- `deploy/prod/DEPLOY.md`, `deploy/prod-local/DEPLOY.md`: how to check for
  failures (`whispercrawl --errors`, exit code for alerting); upgrade note that
  old `_err.txt` files are swept by `--cleanup`.

## Files to change

- `src/whispercrawl/state.py` — schema v5, `errors` table, `ErrorRecord`,
  `record_error` / `clear_errors` / `get_errors`, `mark_step` reset, `forget` /
  `clear`, `NullState`.
- `src/whispercrawl/main.py` — `_report_error` helper, replace `_write_error`
  calls, clear-on-success, per-dir error rows, end-of-run summary, `--errors`
  command + branch.
- `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml` —
  `error_suffix` comments.
- `CLAUDE.md`, `docs/architecture/overview.md`,
  `docs/architecture/decisions/ADR-005-errors-in-index.md`,
  `deploy/prod/DEPLOY.md`, `deploy/prod-local/DEPLOY.md`.
- Tests — below.

## Acceptance Criteria

- [x] A transcription / postprocess / file-summarization failure writes **no**
  file beside the audio; it creates one `errors` row
  (`path`, `engine`, `scope='file'`, `step`, full message) and sets
  `files.status = 'error'`.
- [x] A directory-summarization failure writes no `_<dirname>_err.txt`; it
  creates an `errors` row with `scope='dir'`, `step='dir_summarize'`.
- [x] The next successful run of that step (or `--refresh`) removes the file's /
  directory's `errors` rows; `whispercrawl --errors` then reports nothing for it.
- [x] With two engines, one failing and one succeeding: one `errors` row for the
  failing engine, the succeeding engine's result and the directory output for
  that engine are written, the file is `status='error'` until the failing
  engine succeeds.
- [x] A source file whose `mtime`/`size` changed since the failure discards the
  stale `errors` row on the next `mark_step` (same reset as `asr_results`).
- [x] `whispercrawl --errors` lists every outstanding error grouped by path,
  exits non-zero when any exist and zero when the index is clean.
- [x] `state.enabled: false` → failures still produce `<stem><engine><error_suffix>.txt`
  (unchanged legacy behavior); `--errors` says tracking is disabled.
- [x] `whispercrawl --cleanup` removes leftover legacy `*<error_suffix>.txt`
  files and clears the `errors` table (via `state.clear()`).
- [x] A v4 index opens, gains the `errors` table, and keeps all `files` /
  `asr_results` rows.
- [x] All existing `state`, `main`, `file_walker`, `cleaner` tests pass or are
  updated.

## Tests

- `tests/test_state.py`: v4→v5 opens and creates `errors` without touching
  existing rows; `record_error` → `get_errors` round-trip (file + dir scope);
  `clear_errors(engine=None)` vs one engine; `mark_step` mtime/size mismatch
  drops `errors` rows; `forget` / `clear` clear `errors`; `NullState` no-ops /
  `[]`.
- Pipeline tests (`tests/test_*`):
  - transcribe failure → no `_err.txt` on disk, one `errors` row, `status='error'`;
  - postprocess / file-summarize failure likewise, correct `step`;
  - dir-summarize failure → `scope='dir'` row, no `_<dirname>_err.txt`;
  - fix the failing dependency, rerun → `errors` row gone, `--errors` clean,
    result file written;
  - two engines, one failing → row only for the failer, other engine's outputs
    present;
  - `state.enabled: false` → `_err.txt` written (regression of the old path),
    no crash from the absent table.
- `tests/test_cleanup_cli.py`: `--cleanup` removes a pre-existing legacy
  `*_err.txt` and empties the `errors` table.
- New `tests/test_errors_cli.py`: `--errors` with a seeded index prints the
  grouped listing and exits non-zero; clean index → exits zero; disabled state
  → note + exit zero.

## Out of Scope

- **Structured exception storage** (type, traceback, HTTP status as columns).
  One `message` string is enough; it is the same text `_err.txt` held.
- **Retry / backoff policy.** A file with an `errors` row is re-queued on the
  next run exactly as an `status='error'` file is today; automatic retry
  scheduling is separate.
- **Surfacing errors in the on-disk result** (an "errors" section in
  `<file>.<ext>`). Results are still only written on full success.
- **A machine-readable `--errors --json`** output. Can follow if a wrapper
  needs it; the first cut is human-readable + exit code.
- **Migrating existing `_err.txt` contents into the index.** They are swept by
  `--cleanup`; a fresh failure re-creates the row.
