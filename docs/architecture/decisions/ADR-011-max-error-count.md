# ADR-011: A Failure-Count Brake That Parks the Pipeline

**Date**: 2026-09-03
**Status**: Accepted

## Context

EPIC-055 / ADR-009 made the run tolerant of *any* single failure: a step
records an `errors` row and the batch continues. That is the right default, but
it has no ceiling. When the failure is systemic — the ASR service is down, the
Ollama model name is wrong, a whole directory is corrupt media — every file
fails, every file gets an `errors` row, and the scheduler starts the same doomed
run again on the next tick. Nothing says "stop, something is broken", and an
operator only finds out by noticing the run happened at all.

`max_files_per_run` already establishes the pattern of a top-level integer knob
that bounds a run. The processing index (`db/state.db`, always on — EPIC-051)
already has a `meta` table and survives restarts, so it can hold a counter that
outlives a single run.

## Decision

A new top-level config field `max_error_count` (`Optional[int]`, default `None` =
disabled) drives a circuit breaker.

- **Counter location**: a `meta` row, `error_count`, created lazily. No schema
  bump — `meta` is an existing key/value table.
- **Semantics: consecutive file failures.** `_finalize_file` bumps the counter
  when a file finishes `status='error'` and resets it to `0` when a file
  finishes fully successful. It is a *streak*, not a lifetime total — a mostly
  healthy catalog with the odd bad file never trips.
- **File-count, not file×engine×step.** One file failing on three engines
  advances the counter by one, matching how `max_files_per_run` counts files
  (EPIC-048).
- **Trip = stop this run AND park every later run.** When the counter reaches
  `max_error_count`:
  - the current `per_file` run stops after the tripping file (`run_halted` flag
    checked at the top of the file loop); results already written stay, the
    now-incomplete per-directory summarization pass is skipped, the final
    formatting pass for completed files still runs, the process exits **0**;
  - a pre-flight check at the top of `_run_pipeline` makes every subsequent run
    (`--once`, scheduled, `--refresh`) log an ERROR and return immediately.
- **Un-parking is manual**: `asr-crawler --reset-errors` zeroes the counter and
  exits. It deliberately does *not* clear the `errors` table (that is still
  cleared on the next success, or by `--cleanup`) and does not run the pipeline.
- `--dry-run` uses `NullState`, so it never counts or trips. `--cleanup` zeroes
  the counter via `state.clear()`.
- `per_step` mode does all transcription up front, then finalizes; the brake
  cannot stop it mid-batch, so it completes the in-flight run and the *next* run
  is the one that is parked.

## Alternatives considered

- **A per-run counter that auto-resets each run.** Rejected — it would stop one
  bad run but the scheduler would immediately start another and churn against a
  still-down service. The whole point is to stay stopped until a human looks.
- **Auto-reset after a time-based cooldown (half-open breaker).** Rejected for
  the first cut — "resume automatically in 30 min" is another doomed run if the
  cause is not fixed. Manual reset forces acknowledgement. A timed half-open
  mode can be added later if operators ask.
- **Lifetime total instead of a streak.** Rejected — a long-lived catalog
  accumulates occasional failures; a total would trip eventually on a perfectly
  healthy system.
- **Non-zero exit code when parked.** Rejected for now — "parked" is a
  deliberate state, not a crash, and a cron wrapper that treats exit != 0 as an
  alert would page on every scheduled tick. The ERROR log line and
  `asr-crawler --errors` are the alert surface. A `--strict` opt-in can follow.
- **Counting file×engine failures.** Rejected — inconsistent with
  `max_files_per_run`, and it would make the limit mean different things for a
  one-engine vs. a three-engine config.
- **Raising an exception to unwind the run instead of a flag.** A sentinel
  exception caught outside the file loop would need the whole
  `per_step`/`per_file` block re-indented under a `try`; a `run_halted` dict
  checked at the loop head is a smaller change and keeps the "finish
  consolidating what completed" behaviour obvious.

## Consequences

- Systemic outages now stop after `max_error_count` files instead of burning the
  whole queue, and stay stopped so the scheduler does not churn.
- One new operator action to learn: `asr-crawler --reset-errors` after fixing
  the cause. Documented in `CLAUDE.md`, both `DEPLOY.md` files, and `--help`.
- Disabled by default — existing deployments behave exactly as before until they
  set `max_error_count`.
- No schema change; a pre-EPIC-058 index gains the `error_count` meta row the
  first time a run touches it.
- `_finalize_file` now writes to the index on every successful file (the reset).
  `reset_error_count` skips the write when the counter is already `0`, so the
  common healthy path adds no extra commits.
