# EPIC-058: Stop the Run After Too Many Failed Files (Max Error Count)

## Goal

A safety brake for a bad batch or a down dependency. Today a broken ASR engine,
a wrong Ollama model name, or a directory full of corrupt media makes **every**
file fail — the pipeline dutifully records an `errors` row for each one, writes
nothing, and moves on ([[EPIC-055]], [[EPIC-049]]), and the scheduler starts the
whole thing again on the next tick. Nothing ever says "stop, something is
systemically wrong."

This epic adds a configurable **maximum error count**. A persistent counter in
the processing index tracks consecutive file failures; a fully successful file
resets it to `0`. When it reaches the configured limit the run **stops
immediately** (cleanly, no traceback) and stays stopped — every subsequent run
(scheduled or `--once`) short-circuits with the same message — until an operator
runs `asr-crawler --reset-errors`.

Disabled by default (`max_error_count: null`) — behaviour is unchanged unless the
operator opts in.

## Problem Description

- `_run_pipeline` ([main.py:168](../src/asr_crawler/main.py#L168)) loops over
  every discovered file and, per [[EPIC-055]], contains every failure — there is
  no aggregate failure threshold, so a total outage burns through the entire
  queue (and, with `transcription.engines`, every engine of every file) before
  anyone notices.
- The scheduler ([scheduler.py](../src/asr_crawler/scheduler.py)) re-runs on
  its cron/interval regardless of how the last run went. A down service means
  run after run of nothing-but-errors, each one re-queued because a file with an
  `errors` row is re-processed next time ([[EPIC-049]]).
- `asr-crawler --errors` shows *what* failed but the operator has to notice the
  run happened at all. There is no "the pipeline has given up" state and no
  single knob that says "if more than N files fail, page me instead of grinding."
- The processing index (`db/state.db`, always on — [[EPIC-051]]) is the natural
  place to hold a cross-run counter: it already survives restarts and has a
  `meta` table.

## Scope

### 1. `config.py` — `max_error_count`

- New top-level field on `Config`:
  ```python
  max_error_count: Optional[int] = None  # stop the run after this many consecutive
                                         # file failures; None = disabled
  ```
- `load_config`: read `raw.get("max_error_count")`; validate `>= 1` when not
  `None` (same style as `max_files_per_run`,
  [config.py:264](../src/asr_crawler/config.py#L264)) — `ValueError` otherwise.
- It is a **file-count** threshold, not file×engine×step: one file that fails on
  three engines advances the counter by one (consistent with
  `max_files_per_run` counting files — [[EPIC-048]]).

### 2. `state.py` — a persisted counter in `meta`

- No schema-version bump — the `meta` table already exists
  ([state.py:40](../src/asr_crawler/state.py#L40)); this is a new key,
  `error_count`, created lazily.
- New methods on `ProcessingState`:
  - `get_error_count() -> int` — the stored `error_count` (0 when the key is
    absent).
  - `bump_error_count() -> int` — increment by one, persist, return the new
    value.
  - `reset_error_count() -> int` — set to `0`, persist, return the previous
    value (so `--reset-errors` can report what it cleared).
- `NullState` (the `--dry-run` case): `get_error_count` → `0`,
  `bump_error_count` / `reset_error_count` → no-op returning `0`.
- `clear()` (used by `--cleanup`) also resets `error_count` to `0` — emptying the
  index resets the brake.
- The counter is **not** touched by `mark_step`'s mtime/size reset or by
  `forget(rel)`; it is a run-level aggregate, independent of any one file's row.

### 3. `main.py` — trip and enforce the brake

- **Pre-flight** (top of `_run_pipeline`, before the file loop; also on the
  `--refresh` path): if `config.max_error_count is not None` and
  `state.get_error_count() >= config.max_error_count`, log one ERROR and return
  without processing:
  ```
  error count 12 has reached the limit (10); not processing.
  Review failures with 'asr-crawler --errors', fix the cause, then run
  'asr-crawler --reset-errors' to resume.
  ```
  Return normally (exit 0) so a cron wrapper doesn't treat "deliberately parked"
  as a crash — the WARNING/ERROR line and `--errors` are the alert surface. (If
  a distinct exit code is wanted for alerting, that's a follow-up — see Out of
  Scope.)
- **During the run**, in `_finalize_file` right after
  `_record(rel, fst, "done" if all_ok else "error", …)` (the once-per-file
  status write, both modes):
  - `all_ok` → `state.reset_error_count()` (a good file clears the streak).
  - not `all_ok` → `new = state.bump_error_count()`; if
    `new >= config.max_error_count`, log ERROR and set a `run_halted` flag
    (a one-key dict closed over by the loops — simpler than re-indenting the
    whole `per_step`/`per_file` block under a `try` for a sentinel exception).
  - The whole counter block is guarded by `and not run_halted["stop"]` so once
    tripped it neither re-logs nor mutates the counter for the trailing files a
    `per_step` finalize sweep still visits.
- **`per_file` loop**: checks `run_halted["stop"]` at the top of each iteration
  and `break`s — the tripping file is already finalized (that is what set the
  flag); files after it are never touched.
- **Per-directory pass**: when `run_halted["stop"]`, the whole pass is skipped
  and `dir_file_texts` cleared — a directory summary built from a partial file
  set is misleading. The final formatting pass for already-written per-file
  results still runs.
- `processing_mode: per_step` ([[EPIC-042]]): all files are transcribed/
  processed before the finalize sweep, so the brake cannot stop mid-batch; the
  in-flight run completes and the **next** run is the one parked by the
  pre-flight check.
- `--refresh` ([[EPIC-047]] fast path): counts and trips exactly like a normal
  run — a systemic prompt/model misconfiguration during prompt-iteration should
  also stop rather than churn.
- `--dry-run`: `NullState`, so no counting, no tripping — dry runs never park the
  pipeline.
- Concurrency ([[EPIC-056]]): `_finalize_one` already runs only on the main
  thread, so `bump`/`reset` need no extra locking.

### 4. `main.py` — `--reset-errors` command

- New argparse flag `--reset-errors` (`action="store_true"`), help:
  `"Reset the failure counter that 'max_error_count' uses to park the pipeline, then exit."`
- Branch order in `main()`
  ([main.py:737](../src/asr_crawler/main.py#L737)):
  `--cleanup` → `--reset-errors` → `--errors` → `--refresh` → `--once` /
  `--dry-run` → scheduler.
- New `run_reset_errors(config: Config) -> int` (mirrors `run_errors`'s
  read-side style — [main.py:51](../src/asr_crawler/main.py#L51)):
  opens the index (returns 0 with an "no processing index yet" note if the file
  is absent), calls `reset_error_count()`, prints
  `"error count reset (was N)."` and exits 0. Does **not** clear the `errors`
  table — that stays for `--errors` / the next successful run to clear
  per-[[EPIC-049]]; `--reset-errors` only lifts the brake.
- Does not run the pipeline.

### 5. `main.py` — end-of-run summary line

- The existing end-of-run `state.get_errors()` WARNING
  ([main.py:689](../src/asr_crawler/main.py#L689)): when `max_error_count` is
  set, append the current count and the limit, e.g.
  `"… ; failure counter at 7/10 (resets on the next fully-successful file, or 'asr-crawler --reset-errors')"`.
- When the run stopped because the brake tripped, the ERROR line from §3 is the
  last thing logged before the (still-run) dir/format passes.

### 6. Config files

- `config.yaml`, `deploy/dev/config.yaml`, `deploy/prod/config.yaml`,
  `deploy/prod-local/config.yaml`: add a commented line near `max_files_per_run`:
  ```yaml
  # max_error_count: 20   # stop (and stay stopped) after this many consecutive file
  #                       # failures; clear with `asr-crawler --reset-errors`. Unset = off.
  ```

### 7. Docs

- **`CLAUDE.md`**
  - Key Conventions: a new bullet next to the "Recorded errors" / "Resilient
    step failures" ones — `max_error_count` parks the pipeline after N
    consecutive file failures; a successful file resets the counter; a parked
    pipeline stays parked across scheduled runs until `asr-crawler
    --reset-errors`; disabled by default. Note `--reset-errors` next to
    `--errors`.
  - The `--errors` / deprecated-no-op paragraph area: document `--reset-errors`
    as the counterpart to `--errors`.
- **`docs/architecture/overview.md`**: pipeline-failure section — mention the
  aggregate brake and the `meta.error_count` counter; add `--reset-errors` to
  the CLI list.
- **`docs/architecture/decisions/ADR-011-max-error-count.md`** (new): why a
  cross-run persisted counter (vs. a per-run count that auto-resets); why manual
  reset (operator must acknowledge the systemic failure — an auto-reset breaker
  would just churn on a still-down service); why "consecutive" (reset on
  success) rather than "total ever"; why exit 0 when parked; file-count vs.
  file×engine granularity.
- **`deploy/prod/DEPLOY.md`, `deploy/prod-local/DEPLOY.md`**: operator runbook —
  what "pipeline parked" looks like in the logs, `asr-crawler --errors` to
  triage, fix, `asr-crawler --reset-errors` to resume; recommend setting
  `max_error_count` in production so an ASR/Ollama outage raises an alert instead
  of silently failing every file every run.
- **`README.md`**: one line in the CLI/commands section for `--reset-errors`.

## Files to change

- `src/asr_crawler/config.py` — `max_error_count` field + validation.
- `src/asr_crawler/state.py` — `get_error_count` / `bump_error_count` /
  `reset_error_count` on `ProcessingState` and `NullState`; `clear()` resets it.
- `src/asr_crawler/main.py` — pre-flight check, `_finalize_file` bump/reset +
  `run_halted` flag, `per_file` loop `break`, per-directory pass skip, end-of-run
  summary, `run_reset_errors` + `--reset-errors` flag and branch.
- `config.yaml`, `deploy/dev/config.yaml`, `deploy/prod/config.yaml`,
  `deploy/prod-local/config.yaml` — commented `max_error_count`.
- `CLAUDE.md`, `docs/architecture/overview.md`,
  `docs/architecture/decisions/ADR-011-max-error-count.md`,
  `deploy/prod/DEPLOY.md`, `deploy/prod-local/DEPLOY.md`, `README.md`.
- Tests — below.

## Acceptance Criteria

- [x] `max_error_count: null` / absent → no counting side effects, behaviour
  identical to today (existing suite green).
- [x] `load_config` rejects `max_error_count: 0` and negative values with
  `ValueError`; accepts a positive int and `null`.
- [x] With `max_error_count: 3` and a queue that all fails transcribe:
  the first 3 files record `errors` rows as today; after file 3's finalize the
  run logs the limit-reached ERROR and stops; later files are **not** processed
  (no rows, no results, no `files` rows); the process exits 0; the formatting
  pass for any already-successful files still ran, the incomplete per-directory
  pass is skipped.
- [x] A fully-successful file resets the counter to 0 — 2 failures, 1 success, 2
  failures with `max_error_count: 3` does **not** trip.
- [x] Once tripped, the next `run_pipeline` / `--refresh` / scheduled run
  short-circuits at the pre-flight check (ERROR line, exit 0, nothing processed)
  until `--reset-errors` is run.
- [x] `asr-crawler --reset-errors` sets the counter to 0, prints the previous
  value, exits 0, and does **not** run the pipeline or clear the `errors` table;
  the following run processes files again.
- [x] `--reset-errors` with no index file present prints a note and exits 0.
- [x] `--dry-run` never bumps, resets, or trips the counter.
- [x] `--cleanup` (via `state.clear()`) resets the counter to 0.
- [x] Multi-engine ([[EPIC-048]]): one file failing on 2 of 2 engines advances
  the counter by 1, not 2.
- [x] `KeyboardInterrupt` mid-run still records `status='partial'` and does not
  itself bump the counter ([[EPIC-055]] behaviour intact — no counter mutation
  on the interrupt path).
- [x] The counter persists across process restarts (it lives in `meta`).
- [x] Existing `state`, `main`, `config`, `file_walker` tests pass (494 green).

## Tests

- `tests/test_config.py`: `max_error_count` default `None`; `2` accepted; `0` /
  `-1` → `ValueError`; round-trips onto `Config`.
- `tests/test_state.py`: `get_error_count` on a fresh index → `0`;
  `bump_error_count` returns 1, 2, 3 and persists across a re-`open`;
  `reset_error_count` returns the previous value and zeroes it; `clear()` zeroes
  it; `NullState` → `0` / no-ops.
- `tests/test_max_error_count.py` (new — pipeline integration):
  - `max_error_count: 3`, 5 files all failing transcribe → 3 `errors` rows +
    exactly 3 `files` rows, run stops, exit 0;
  - interleave a success → counter resets, brake not tripped, all 5 processed;
  - pre-tripped index (seed `error_count = 5`, `max_error_count: 3`) → run does
    nothing, exit 0; then `run_reset_errors` → next run processes;
  - two engines both failing for one file → counter == 1;
  - `--dry-run` with a pre-tripped index → counter unchanged;
  - `run_reset_errors` leaves `errors` rows intact; no index → returns 0.

## Out of Scope

- **A non-zero exit code when parked.** First cut exits 0 (parked is a
  deliberate state, not a crash); a `--strict` / config knob for cron alerting
  can follow.
- **Auto-reset after a cooldown / time window.** The reset is manual on purpose —
  an operator acknowledges the systemic failure. A time-based half-open breaker
  is a separate epic.
- **A per-directory or per-engine failure threshold.** One global file-count
  counter only.
- **Counting file×engine×step failures** instead of files. Files match
  `max_files_per_run`.
- **Surfacing the counter in `asr-crawler --errors` output.** `--errors` stays
  the "what failed" view; the end-of-run WARNING carries the count. Can be added
  later if operators want it in one place.
- **`--reset-errors` also clearing the `errors` table.** That remains
  [[EPIC-049]]'s job (cleared on the next success, or by `--cleanup`).
- **Pausing the APScheduler job itself** when parked. The scheduler keeps firing;
  each run short-circuits cheaply at the pre-flight check.
