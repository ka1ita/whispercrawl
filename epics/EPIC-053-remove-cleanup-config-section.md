# EPIC-053: Remove the `cleanup:` Config Section — Drop `CleanupConfig` / `cleanup.on`

## Goal

The `cleanup:` block in `config.yaml` has one field left after [[EPIC-052]]:

```yaml
cleanup:
  on: success   # "success" | "always"
```

`on` gates the per-file post-run sweep in `--once --cleanup`: `success` removes a
file's consolidated result only when every step for it succeeded, `always`
removes it regardless. Since [[EPIC-047]] / [[EPIC-049]] / [[EPIC-051]] **nothing
is ever written beside the audio on failure** — a failed file has no result file
to remove — so `success` and `always` now produce identical behavior. The knob
configures a distinction that no longer exists.

This epic removes the whole section:

- `CleanupConfig` and `Config.cleanup` — **gone**.
- The `Cleaner` no longer takes a config; the post-run per-file sweep keeps the
  current default behavior hardcoded (clean a file's result only after every
  step for that file succeeded).
- The standalone `--cleanup` flag, `run_cleanup()`, and the `--once --cleanup`
  post-run sweep **stay** — only their configurability goes away.

## Depends on

[[EPIC-052]] (reduced `CleanupConfig` to the single `on` field and removed
`targets`; the legacy `*_err.txt` sweep is already gone).

## Problem Description

- `CleanupConfig.on` ([config.py:81](../src/whispercrawl/config.py#L81)) is the
  last survivor of a section that has been whittled down across EPIC-051/052.
  Its two values are now behaviorally identical because the pipeline never
  produces a partial result to protect.
- `Cleaner.__init__` takes `config: CleanupConfig` only to read `.on` in
  `clean()` ([cleaner.py:47-49](../src/whispercrawl/pipeline/cleaner.py#L47)).
- `_run_pipeline` threads `config.cleanup` into the `Cleaner` constructor
  ([main.py:224](../src/whispercrawl/main.py#L224)).

Net effect for a reader of the config: a `cleanup:` section that looks like it
controls something, guarding a code path whose two branches do the same thing.

## Scope

### 1. `config.py`

- Remove the `CleanupConfig` dataclass.
- Remove the `cleanup: CleanupConfig` field from `Config`
  ([config.py:153](../src/whispercrawl/config.py#L153)).
- Remove `cleanup=_build(CleanupConfig, raw.get("cleanup", {}))` from
  `load_config` ([config.py:277](../src/whispercrawl/config.py#L277)).
- Deprecated-key WARNING loop: replace the `("cleanup", "targets", …)` entry
  (added in EPIC-052) with `("cleanup", "on", _epic_053)` where

  ```python
  _epic_053 = (
      "EPIC-053 (the cleanup sweep is not configurable; --cleanup removes the "
      "consolidated result files this version writes)"
  )
  ```

  Also warn when `raw` contains a `cleanup` key with no recognized sub-field
  (e.g. an empty `cleanup: {}` or a stale `cleanup: { targets: [...] }`): a
  single `"cleanup: is deprecated and ignored since EPIC-053"` covers the
  whole-section case. `_build` already drops unknown keys, so old configs load.

### 2. `pipeline/cleaner.py`

- `Cleaner.__init__(self, output_format="txt", engine_labels=None)` — drop the
  `config` parameter and `self.config`.
- `clean(self, file_path, success)`: keep the `success` gate inline —

  ```python
  def clean(self, file_path: Path, success: bool) -> None:
      """Remove the consolidated result document for file_path after a
      --once --cleanup run, but only when every step for the file succeeded."""
      if not success:
          return
      ...
  ```

  (Previously `if self.config.on == "success" and not success: return` — the
  `on == "always"` escape hatch is dropped.)
- `clean_other_formats` — unchanged.
- Module docstring / `import` of `CleanupConfig` — removed.

### 3. `main.py`

- `_run_pipeline()`: `cleaner = Cleaner(config.cleanup, fmt, engine_labels=...)`
  → `cleaner = Cleaner(fmt, engine_labels=...)`
  ([main.py:224-225](../src/whispercrawl/main.py#L224)).
- `cleaner.clean(file_path, all_ok)` ([main.py:456](../src/whispercrawl/main.py#L456))
  — unchanged.
- `run_cleanup()` — unchanged (never consulted `cleanup.on`; the standalone
  `--cleanup` always removes every current-version result).
- `--cleanup` `--help` text — unchanged; confirm it does not mention a config
  key.

### 4. Config templates

`config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`:

- Delete the `cleanup:` block and its comment header. Replace with a short
  comment only (no live keys):

  ```yaml
  # ── Cleanup ──────────────────────────────────────────────────────────────────
  # `whispercrawl --cleanup` (alone, or with `--once`) deletes the consolidated
  # result files this version writes — <file>.<ext> and _<dirname>.<ext>, one set
  # per ASR engine, any formatter extension — and empties the processing index.
  # It is not configurable. Pre-047 sidecars (_fix/_sum/_all/_concat) and _err.txt
  # files are left alone — delete those by hand when upgrading an old catalog.
  # With `--once --cleanup` a file's result is removed only after every pipeline
  # step for that file succeeded.
  ```

### 5. Docs

- `CLAUDE.md`:
  - **Key Conventions** — the `--cleanup` sentence: drop any implication that a
    `cleanup:` section exists; state the sweep is not configurable and that
    `--once --cleanup` removes a file's result only on full success.
  - Any other `cleanup:` / `cleanup.on` mention — remove.
- `docs/architecture/overview.md`:
  - Delete the `CleanupConfig` table row
    ([overview.md:101](../docs/architecture/overview.md#L101)).
  - `--cleanup` prose ([overview.md:112](../docs/architecture/overview.md#L112),
    [overview.md:114](../docs/architecture/overview.md#L114)) — keep the flag
    description; drop the `on` / `always` mention.
- `docs/architecture/decisions/` — a short ADR (or an amendment to the EPIC-052
  ADR): the cleanup sweep has no configuration; `--once --cleanup` always
  protects a file whose run had an error (a moot guarantee now that failures
  write nothing, but kept as the stated contract). Cross-reference
  [[EPIC-052]] and [[EPIC-051]].
- `deploy/prod/DEPLOY.md`, `deploy/prod-local/DEPLOY.md`: the "Cleanup output
  files" section — remove any reference to `cleanup.on` / `cleanup:` config;
  `service-cleanup.sh` behavior is unchanged.

### 6. Tests

- `tests/test_config.py`: `Config()` has no `cleanup` attribute; a YAML file
  that still sets `cleanup: { on: always }` (or `cleanup: {}`) loads without
  error and logs one deprecation WARNING.
- `tests/test_cleanup_cli.py`: drop every `CleanupConfig(...)` / `cleanup=`
  construction and `config.cleanup` reference; `Cleaner(...)` new signature;
  `--cleanup` still removes `<file>.<ext>` / `_<dirname>.<ext>` (single- and
  multi-engine) and empties the index.
- `tests/test_pipeline_err_cleanup.py` and any other suite constructing a
  `Cleaner` or `CleanupConfig` — update to the new signature. Add/keep a case:
  `--once --cleanup` with one failing step leaves other files' results removed
  and writes nothing for the failed file (no partial to clean).
- Grep the suite for `CleanupConfig`, `cleanup=`, `config.cleanup`, `.on` and
  clear every hit.

## Acceptance Criteria

- [x] `CleanupConfig` does not exist; `Config` has no `cleanup` field; nothing
  in `src/` imports or references either.
- [x] `Cleaner(output_format, engine_labels=...)` takes no config; `clean()`
  removes a file's consolidated result only when `success` is true.
- [x] A config that still sets `cleanup.on` (or an empty `cleanup:` block) loads
  without error and logs one deprecation WARNING.
- [x] `whispercrawl --cleanup` behavior is unchanged — removes every
  current-version `<file>.<ext>` / `_<dirname>.<ext>` (per engine, any
  extension) and empties the processing index.
- [x] `whispercrawl --once --cleanup` removes each successfully-processed file's
  result after the run and leaves nothing for a file whose run recorded an
  error.
- [x] Config templates have no `cleanup:` keys — only a descriptive comment.
- [x] Docs contain no `cleanup:` config section or `cleanup.on` mention.
- [x] Full test suite green.

## Out of Scope

- **Removing `--cleanup` / `run_cleanup()` / the `--once --cleanup` sweep.**
  The flag stays; only its configurability is removed.
- **Changing what `--cleanup` deletes** (still the current-version consolidated
  results + the index; pre-047 sidecars untouched — [[EPIC-052]]).
- **`service-cleanup.sh`** and the deploy wrappers — they call
  `--once --cleanup` and need no change.
- **Schema or index-format changes.** `state.clear()` is untouched.
