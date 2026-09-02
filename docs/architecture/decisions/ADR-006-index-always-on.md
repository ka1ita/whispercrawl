# ADR-006: The Processing Index Is Mandatory; Cleanup Targets Only Current Outputs

**Date**: 2026-09-02
**Status**: Accepted

## Context

EPIC-040 introduced the persisted processing index behind `state.enabled`
(default true), with `state.store_text` (default true) gating the raw/fixed
transcript storage that powers `--refresh`. [ADR-005](ADR-005-errors-in-index.md)
then moved pipeline failures into the index, keeping the `<file>_err.txt`
sidecar (and the four `*.error_suffix` config fields) only as the
`state.enabled: false` fallback.

In practice no deployment turns either toggle off. `state.enabled: false` loses
resume, `--refresh`, `--errors`, and scatters `_err.txt` files back into the
media tree — the exact thing EPIC-047/049 removed. `store_text: false` saves a
few MB and breaks `--refresh`. Both existed only as configuration surface and as
a second code path (`NullState` for the disabled index, an `isinstance` branch
in `main.py`, a sidecar-writing `_report_error` fallback, two `if
store_text:` guards).

Cleanup carried a parallel legacy load: `cleanup.targets` defaulted to
`["", "_fix", "_sum", "_all", "_concat", "_diarize.json"]` — only `""` is a
current output — plus a recursive `*<error_suffix>.txt` sweep, both there to
tidy a pre-047/049 catalog on upgrade.

## Decision

**The index is always on and always stores transcript text (EPIC-051).**

- `StateConfig` keeps only `path`. `state.enabled` / `state.store_text` in a
  config file are ignored with a deprecation WARNING (the EPIC-047 pattern).
- `open_state(path, config_root, watch_dir=None)` always returns a
  `ProcessingState`. `NullState` stays, but only as the `--dry-run` stand-in
  (a dry run records nothing).
- `main.py` loses the disabled-index branch: `_report_error` always calls
  `state.record_error`, `_write_error` is deleted, the `store_text` guards and
  the `--refresh` precondition check are gone.

**`--cleanup` removes only what the running version produces (EPIC-052).**

- `CleanupConfig` keeps only `on` (`success` | `always`). `cleanup.targets` is
  ignored with a deprecation WARNING.
- `run_cleanup` / `Cleaner` remove the per-file result `<file>.<ext>` and the
  per-directory result `_<dirname>.<ext>` (one set per ASR engine, in every
  formatter extension), and empty the processing index. Nothing else.
- The four `*.error_suffix` fields and the `run_cleanup` `*_err.txt` sweep are
  removed. Failures never touch disk, so the fields had no readers left.
- Pre-047/049 sidecars (`_fix` / `_sum` / `_all` / `_concat` / `_err.txt`) are
  an operator concern: `find <watch_dir> \( -name '*_fix.*' … \) -delete` on
  upgrade, documented in both `DEPLOY.md` files.

No schema change — existing `state.db` files open untouched.

## Alternatives considered

- **Keep `state.path` out too, flatten to a top-level `state_path`.** Rejected
  — the nested key matches existing configs and EPIC-043; the churn buys
  nothing.
- **Keep `store_text` as a size/feature trade-off.** Rejected — the DB stays
  safe to delete, and `--refresh` is worth far more than the bytes.
- **Keep a `--cleanup --legacy` mode (or a one-shot migration command) for old
  sidecars.** Rejected — a documented `find … -delete` is simpler than carrying
  the sweep code and its tests forever.
- **Have `--cleanup` remove only the current `formatter.format` extension.**
  Rejected — `--cleanup` is a reset; if the format changed, the stale `.txt`
  should go too.

## Consequences

- One code path for the index; `main.py`, `state.py`, and `cleaner.py` shed
  their disabled-state / legacy-target branches.
- `--refresh` and `--errors` always work — no precondition to explain.
- A pre-upgrade catalog needs one manual `find … -delete`; after that
  `--cleanup` is a clean reset.
- Config files drop the `state:` block to a commented `path:` hint and the
  `cleanup:` block to `on:` only; four `error_suffix` lines removed.
- Tests that constructed `StateConfig(enabled=…)`, `CleanupConfig(targets=…)`,
  or `error_suffix=…` were updated; the `state.enabled: false` regression tests
  were deleted.
