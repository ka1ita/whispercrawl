# EPIC-051: The Processing Index Is Always On — Remove `state.enabled` / `state.store_text`

## Goal

The persisted processing index (`db/state.db`) is no longer optional. Drop the
two toggles that could turn it (or its text storage) off:

- `state.enabled` — gone. The index is always opened.
- `state.store_text` — gone. Raw ASR + post-processed text are always stored.

`state.path` **stays** — an operator can still point the index at a different
(or separately mounted / writable) location, as [[EPIC-043]] intended.

After this epic there is exactly one code path: every run opens a real
`ProcessingState`. `--refresh` and `--errors` always work. Nothing is ever
written beside the audio on failure — the `<file>_err.txt` runtime fallback
([[EPIC-049]]) is removed (the legacy `_err.txt` *cleanup sweep* stays for
pre-049 upgrades).

## Problem Description

`state.enabled: false` and `state.store_text: false` exist but earn nothing:

- **They fork the codebase.** `open_state` returns a `NullState`; `main.py`
  carries an `_index_errors = isinstance(state, ProcessingState)` branch, a
  `_report_error` fallback that writes `<file>_err.txt`, two `if
  config.state.store_text:` guards, and a `--refresh` precondition check. Every
  one of these is dead weight for the default (and only sensible) configuration.
- **Disabling the index removes features silently.** With `state.enabled:
  false` there is no resume, no `--refresh`, no `--errors`, and failures scatter
  `_err.txt` files back into the media tree — the exact thing [[EPIC-047]] /
  [[EPIC-049]] set out to stop. There is no real deployment that wants this.
- **`store_text: false` is a trap.** It saves a few MB of SQLite and in
  exchange breaks `--refresh` and per-step resume-from-disk. Nobody sets it on
  purpose.
- `NullState` is only ever the `--dry-run` stand-in now (dry run makes no API
  calls, so it never records anything) — it does not need to model a "disabled
  index" configuration, just "don't touch the DB during a dry run".

## Scope

### 1. `config.py`

- `StateConfig`: remove the `enabled` and `store_text` fields. Keep `path`
  only:

  ```python
  @dataclass
  class StateConfig:
      path: Optional[str] = None   # default: <config dir>/db/state.db
  ```

- `load_config`: the `state_cfg.path` default-resolution block is unchanged
  (`_build` already drops unknown keys, so a stale `enabled:` / `store_text:`
  in a YAML file is ignored, not an error).
- Add `state.enabled` and `state.store_text` to the existing deprecated-key
  WARNING loop (same pattern as the EPIC-047 `replace_transcription` /
  `output_suffix` warnings): if `raw["state"]` contains either key, log
  `"state.%s is deprecated and ignored since EPIC-051 (the processing index is
  always enabled and always stores transcript text)"`.

### 2. `state.py`

- `open_state(enabled, path, config_root, watch_dir=None)` → drop the `enabled`
  parameter: `open_state(path, config_root, watch_dir=None)`. It always
  migrates the legacy DB (if any) and returns `ProcessingState.open(resolved)`.
- `NullState` **stays** (still the `--dry-run` stand-in) but its docstring
  changes from "used when the persisted index is disabled" to "no-op index used
  for `--dry-run`, which records nothing".
- No schema change, no `SCHEMA_VERSION` bump — the DB file is untouched.

### 3. `main.py`

- `run_errors()`: remove the `if not config.state.enabled:` early-return block.
  Always resolve `config.state.path` (always set by `load_config`) and open the
  index read-only. (Also drop the dead `or default_state_path(config.watch_dir)`
  fallback — `load_config` always resolves `state.path`.)
- `run_cleanup()` ([main.py:171](../src/whispercrawl/main.py#L171)): remove the
  `if config.state.enabled:` guard — always clear the index at
  `config.state.path` when it exists (dry-run still just logs).
- `run_pipeline()`:
  - Remove the `if refresh and not (config.state.enabled and
    config.state.store_text): return` precondition — `--refresh` always has the
    index and stored text now. (A file with no stored transcript for an engine
    is still individually skipped inside `_run_pipeline`, unchanged.)
  - `state = NullState() if dry_run else open_state(config.state.path,
    config.watch_dir, watch_dir=config.watch_dir)`.
- `_run_pipeline()`:
  - Remove `_index_errors` and simplify `_report_error` to call
    `state.record_error(...)` unconditionally (`NullState.record_error` is a
    no-op, so `--dry-run` stays silent). The `err_path` parameter and the
    `<file>_err.txt` write branch go away.
  - Delete the module-level `_write_error()` helper (now unused).
  - Remove the two `if config.state.store_text:` guards
    ([main.py:405](../src/whispercrawl/main.py#L405),
    [main.py:458](../src/whispercrawl/main.py#L458)) — always call
    `state.save_text(...)`.
- `--help` text for `--refresh`
  ([main.py:640](../src/whispercrawl/main.py#L640)): drop "Needs state.enabled +
  state.store_text."

### 4. `error_suffix` config fields — deferred to [[EPIC-052]]

EPIC-051 stops anything from *writing* `<file>_err.txt` at runtime — the
`_report_error` sidecar branch and `_write_error()` are removed here. That
leaves the four `*.error_suffix` config fields and `run_cleanup`'s legacy
`*_err.txt` sweep vestigial (referenced, no runtime effect). [[EPIC-052]]
removes them along with the pre-047/049 `cleanup.targets` legacy entries. This
epic leaves those two things in place.

### 5. `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`

Replace the `state:` block with a commented-out path-override hint:

```yaml
# Persisted index of processed files — a SQLite file at <config dir>/db/state.db
# (always on). It records done/error per file so runs resume after interruption,
# stores each file's raw + post-processed transcript to power `whispercrawl
# --refresh`, and records failures for `whispercrawl --errors`.
# Deleting the file is safe: the next run re-derives it from existing outputs.
# state:
#   path: ./db/state.db   # override the default location (own mount, writable disk, …)
```

(`deploy/prod` and `deploy/prod-local`: `# path: /db/state.db` and keep the
"a legacy …/.whispercrawl/state.db is moved here automatically" line.)

### 6. Docs

- `CLAUDE.md` Key Conventions:
  - **Persisted index** bullet: drop `(state.enabled: true, default)` →
    "Persisted index (`db/state.db`, always on)".
  - **Stored transcript text** bullet: drop `(state.store_text: true, default)`
    → "The index always stores each file's raw ASR transcript and
    post-processed text".
  - **`--refresh`** bullet: remove "Needs `state.enabled` + `state.store_text`."
  - **Recorded errors** bullet: remove "With `state.enabled: false` the
    `<file>_err.txt` sidecar is the fallback." — there is no such fallback now.
  - Pipeline prose ("Only when `state.enabled: false` is a `<file>_err.txt`
    sidecar written instead"): delete that sentence.
- `docs/architecture/overview.md`: `state.py` section, the "Stored transcript
  text and `--refresh`" paragraph, the "Recorded errors" paragraph, the
  `StateConfig` table row, and the two "When `state.enabled: false` …" sidebars
  (lines ~35, 43, 45, 88, 104, 122, 148) — drop every mention of disabling the
  index or `store_text`; the `_err.txt` sidecar is described as pre-049 history
  only.
- `docs/architecture/decisions/ADR-005-errors-in-index.md`: the
  "`state.enabled: false` keeps the sidecar" bullet becomes a note that
  EPIC-051 removed that fallback; a short ADR (or an amendment to ADR-004 /
  whichever covers the index) recording that the index is now mandatory.
- `deploy/prod/DEPLOY.md`, `deploy/prod-local/DEPLOY.md`: remove "Disable with
  `state.enabled: false`" and the `store_text: false` guidance; `--refresh` /
  `--errors` are always available; drop the "with `state.enabled: false` the
  sidecar behavior is unchanged" lines.

### 7. Tests

- `tests/test_config.py`: `state.enabled` / `state.store_text` in a YAML file
  load without error and log the deprecation WARNING; `StateConfig` has no
  `enabled` / `store_text` attribute; `state.path` default + explicit override
  still resolve as in [[EPIC-043]].
- `tests/test_state.py`: `open_state(path, config_root)` (new signature) returns
  a `ProcessingState`; legacy-migration tests updated to the new arg list;
  `NullState` still exposes the full no-op surface.
- `tests/test_refresh.py`: drop the "`--refresh` errors when `state.enabled:
  false`" / "`store_text: false`" cases; `--refresh` works from a default
  config.
- `tests/test_errors_cli.py`: drop the "disabled state → note + exit zero"
  case; `--errors` always opens the index.
- `tests/test_pipeline_err_cleanup.py`, `tests/test_processing_index.py`,
  `tests/test_processing_mode.py`, `tests/test_multi_engine.py`: remove any
  `state.enabled: false` / `store_text: false` construction; the
  "`state.enabled: false` → `_err.txt` written" regression case is deleted (the
  fallback no longer exists).
- `--cleanup` still removes a pre-existing legacy `*_err.txt` file and empties
  the `errors` table — keep that test.

## Files to change

- `src/whispercrawl/config.py` — `StateConfig` fields, deprecated-key warning.
- `src/whispercrawl/state.py` — `open_state` signature, `NullState` docstring.
- `src/whispercrawl/main.py` — `run_errors`, `run_cleanup`, `run_pipeline`,
  `_run_pipeline` (`_report_error`, `_write_error` removal, `store_text`
  guards), `--help`.
- `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`.
- `CLAUDE.md`, `docs/architecture/overview.md`,
  `docs/architecture/decisions/ADR-005-errors-in-index.md` (+ possibly a new
  ADR), `deploy/prod/DEPLOY.md`, `deploy/prod-local/DEPLOY.md`.
- Tests as above.

## Acceptance Criteria

- [x] `StateConfig` exposes only `path`; there is no `enabled` or `store_text`
  attribute anywhere in the code.
- [x] A config file that still sets `state.enabled: false` or
  `state.store_text: false` loads without error, logs a deprecation WARNING for
  each key, and runs with the index fully enabled.
- [x] Every run (normal, `--once`, `--refresh`, `--errors`, `--cleanup`) opens a
  real `ProcessingState`; only `--dry-run` uses `NullState`.
- [x] A step failure records an `errors` row and writes **nothing** beside the
  audio under any configuration; `_write_error` no longer exists.
- [x] Raw ASR and post-processed text are always written to `asr_results`;
  `--refresh` runs from a stock config with no extra flags.
- [x] `whispercrawl --errors` always inspects the index (no "tracking disabled"
  branch); exits non-zero iff any error row exists.
- [x] `run_cleanup` empties the `errors` table via `state.clear()`; nothing
  writes a `<file>_err.txt` at runtime (`_write_error` is gone). The vestigial
  `error_suffix` fields and the legacy `*_err.txt` sweep are removed in
  [[EPIC-052]].
- [x] `state.path` override still works verbatim; the legacy
  `.whispercrawl/state.db` auto-migration ([[EPIC-043]]) is unchanged.
- [x] `config.yaml` and both deploy configs have no `state.enabled` /
  `state.store_text`; the `state:` block is a commented `path:` hint.
- [x] Docs contain no instruction to disable the index or text storage; the
  `_err.txt` sidecar is described only as pre-049 history.
- [x] Full test suite green.

## Out of Scope

- **Schema / DB-file changes.** No `SCHEMA_VERSION` bump; existing `state.db`
  files open untouched.
- **Removing `NullState`.** It stays as the `--dry-run` stand-in.
- **Removing the `error_suffix` config fields and the legacy `_err.txt` /
  `_fix` / `_sum` / `_all` / `_concat` cleanup targets.** Handled by
  [[EPIC-052]].
- **Removing the `state:` key entirely** (flattening `state.path` to a
  top-level `state_path`). The nested key is kept for continuity with existing
  configs and [[EPIC-043]].
- **Auto-deleting a stale `state.db`** or any change to how the index rebuilds
  itself from output files (EPIC-040).
