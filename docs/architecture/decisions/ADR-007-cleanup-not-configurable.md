# ADR-007: The Cleanup Sweep Has No Configuration

**Date**: 2026-09-02
**Status**: Accepted

## Context

[ADR-006](ADR-006-index-always-on.md) / EPIC-052 reduced `CleanupConfig` to a
single field, `on` (`success` | `always`). It gated the per-file post-run sweep
of `--once --cleanup`: `success` removed a file's consolidated result only when
every step for it succeeded, `always` removed it regardless.

Since EPIC-047 / EPIC-049 / EPIC-051 the pipeline never writes anything beside
the audio on failure — a failed file has no result file to remove. `success` and
`always` therefore produce identical behavior. `CleanupConfig` was the last
survivor of a `cleanup:` section whittled down across EPIC-051/052, and
`Cleaner.__init__` took a `config` argument only to read `.on`.

## Decision

**The `cleanup:` config section is removed entirely (EPIC-053).**

- `CleanupConfig` and `Config.cleanup` are deleted. A `cleanup:` key in a config
  file (any sub-fields) is ignored with a single deprecation WARNING (the
  EPIC-047 pattern).
- `Cleaner(output_format, engine_labels=None)` takes no config. `Cleaner.clean`
  keeps the previous default hardcoded: it removes a file's consolidated result
  only when the run for that file fully succeeded (`if not success: return`).
- `--cleanup`, `run_cleanup()`, and the `--once --cleanup` post-run sweep are
  unchanged in behavior — only their configurability is gone. The standalone
  `--cleanup` still removes every current-version `<file>.<ext>` /
  `_<dirname>.<ext>` (per engine, any formatter extension) and empties the
  processing index.

No schema change.

## Alternatives considered

- **Keep `cleanup.on` for the `always` escape hatch.** Rejected — with no
  partial results ever written, `always` and `success` are indistinguishable;
  the knob documents a difference that no longer exists.
- **Remove `--cleanup` / the post-run sweep too.** Rejected — the reset command
  and the rescan-style "process then delete" workflow still have users; only the
  config surface is dead weight.

## Consequences

- `config.py`, `main.py`, and `cleaner.py` shed the last `cleanup`-config
  branch; `Cleaner` no longer imports from `config`.
- Config files drop the `cleanup:` block to a descriptive comment with no live
  keys.
- Tests that constructed `CleanupConfig(...)` or passed `cleanup=` / read
  `config.cleanup` were updated to the new `Cleaner` signature.
