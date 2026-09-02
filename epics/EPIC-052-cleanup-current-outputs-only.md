# EPIC-052: Cleanup Removes Only the Current Version's Outputs — Drop `error_suffix` and Legacy `cleanup.targets`

## Goal

`--cleanup` and the `--once --cleanup` post-run sweep should remove exactly
what **this** version of the service writes and nothing else:

- the consolidated per-file result `<file>.<ext>` (per ASR engine:
  `<file>_<name>.<ext>`)
- the consolidated per-directory result `_<dirname>.<ext>` / `<dirname>.<ext>`
  (per engine)
- stale-extension copies of those from a previous `formatter.format`
  (`clean_other_formats`)
- the processing index `errors` table (`state.clear()`)

Everything tied to pre-047/pre-049 layouts is removed from the code and config:

- the `cleanup.targets` list (`_fix` / `_sum` / `_all` / `_concat` /
  `_diarize.json`) — **gone**; there is nothing to configure, cleanup always
  targets the one result document.
- the four `*.error_suffix` config fields
  (`transcription`, `postprocessing`, `file_summarization`,
  `dir_summarization`) — **gone**. After [[EPIC-051]] nothing writes a
  `<file>_err.txt` at runtime; this epic drops the now-unused fields and the
  `run_cleanup` `*_err.txt` sweep.

Old sidecars from a pre-upgrade catalog (`_fix.txt`, `meeting_err.txt`, …) are
**not** the service's concern anymore — an operator upgrading a large old
catalog deletes them by hand (or with one `find … -delete`). This is a
deliberate simplification, not an oversight.

## Depends on

[[EPIC-051]] (the runtime `_err.txt` fallback and `_write_error()` are already
removed there; `error_suffix` is only referenced by the legacy sweep by the
time this epic starts).

## Problem Description

`cleanup` currently carries two eras of output layout:

- `CleanupConfig.targets` defaults to
  `["", "_fix", "_sum", "_all", "_concat", "_diarize.json"]`
  ([config.py:87](../src/whispercrawl/config.py#L87)). Only `""` is a current
  output. The rest are pre-047 scattered sidecars kept "so one `--cleanup` pass
  sweeps an upgraded catalog" — a migration aid that has outlived a run or two
  of every real deployment and now just complicates `Cleaner`
  ([cleaner.py](../src/whispercrawl/pipeline/cleaner.py)) and `run_cleanup`
  ([main.py:102](../src/whispercrawl/main.py#L102)) with a `for suffix in
  targets` loop and a `.json` special case.
- `run_cleanup` also does a recursive `rglob(f"*{suffix}.txt")` sweep for every
  `error_suffix` ([main.py:153](../src/whispercrawl/main.py#L153)). After
  [[EPIC-051]] nothing writes those files; the sweep only ever finds pre-049
  leftovers.
- The four `error_suffix` fields are dead config once [[EPIC-051]] lands — no
  code path reads them except that one legacy sweep.

Net effect for a reader of the config or the cleaner: several knobs and code
branches that describe a layout the service no longer produces.

## Scope

### 1. `config.py`

- `TranscriptionConfig`: remove `error_suffix: str = "_err"`.
- `OllamaStepConfig`: remove `error_suffix: str = "_err"` (drops it from
  `postprocessing`, `file_summarization`, `dir_summarization` which subclass /
  reuse it).
- `CleanupConfig`: remove the `targets` field. Keep only `on`:

  ```python
  @dataclass
  class CleanupConfig:
      on: str = "success"  # "success" | "always" — clean only after full success, or always
  ```

- `load_config`: extend the existing deprecated-key WARNING loop (EPIC-047
  pattern) to also fire for `cleanup.targets` and for `error_suffix` under any
  of the four sections:
  `"cleanup.targets is deprecated and ignored since EPIC-052 (cleanup always
  targets the one consolidated result file)"` and
  `"%s.error_suffix is deprecated and ignored since EPIC-052 (failures are
  recorded in the processing index; run 'whispercrawl --errors')"`.
  `_build` already drops the unknown keys, so old configs still load.

### 2. `pipeline/cleaner.py`

- `Cleaner.__init__(self, config: CleanupConfig, output_format="txt",
  engine_labels=None)` — unchanged signature; `config` is now only consulted
  for `.on`.
- `clean(self, file_path, success)`: drop the `for suffix in self.config.targets`
  loop and the `.json` branch. For each engine label, remove the single
  `file_path.stem + label + self._ext` result if present (honoring the
  `on == "success"` gate).
- `clean_other_formats(self, file_path, dry_run=False)`: drop the
  `suffix_labels` parameter. For each engine label and each *other* extension
  in `_ALL_EXTS - {self._ext}`, remove `file_path.stem + label + ext`.
- Docstrings updated to say "the consolidated result document".

### 3. `main.py`

- `run_cleanup()`:
  - Delete `targets = config.cleanup.targets` and both nested `for suffix in
    targets` loops. Per media file and per engine label, probe and remove the
    one `output_path(media_path, label, fmt)` result.
  - Per directory + engine label, probe and remove
    `output_path(dir_path / (dir_prefix + dir_path.name + label), "", fmt)`.
  - Delete the whole `err_suffixes` / `rglob(f"*{suffix}.txt")` sweep block
    ([main.py:153-169](../src/whispercrawl/main.py#L153)).
  - Keep the `state.clear()` step (empties `files` / `asr_results` / `errors`).
  - Keep the `removed == 0 → "No output files found"` log.
- `_run_pipeline()`:
  - `_rescan_labels = [...]` ([main.py:286](../src/whispercrawl/main.py#L286))
    — delete; update the two `cleaner.clean_other_formats(...)` calls
    ([main.py:294](../src/whispercrawl/main.py#L294),
    [main.py:354](../src/whispercrawl/main.py#L354)) to the new signature
    (`file_path`, optional `dry_run`).
  - `cleaner.clean(file_path, all_ok)` call
    ([main.py:524](../src/whispercrawl/main.py#L524)) — unchanged.
  - Confirm no `config.*.error_suffix` reference survives anywhere (the
    `_finalize_file` stale-`_err.txt` block is already removed by [[EPIC-051]]).

### 4. Config templates

`config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`:

- Remove the `error_suffix:` line (and its two-line comment) from
  `transcription`, `postprocessing`, `file_summarization`, `dir_summarization`.
- Replace the `cleanup:` section:

  ```yaml
  # ── Cleanup (--cleanup, or --once --cleanup) ──────────────────────────────────
  # Removes the consolidated result files this version writes:
  #   <file>.<ext> and _<dirname>.<ext>  (one set per ASR engine)
  # plus stale-extension copies left by a previous formatter.format, and empties
  # the processing index. Pre-047 sidecars (_fix/_sum/_all/_concat) and _err.txt
  # files are left alone — delete those by hand when upgrading an old catalog.
  #   on: success  → clean only when every pipeline step for the file succeeded
  #      always   → clean even after a failed step
  cleanup:
    on: success
  ```

### 5. Docs

- `CLAUDE.md`:
  - **Key Conventions** — the `--cleanup` sentence: replace "`--cleanup` sweeps
    the legacy `_fix` / `_sum` / `_all` / `_concat` files from a pre-047
    catalog" with "`--cleanup` removes the consolidated result files this
    version writes and empties the processing index; pre-047 sidecars and
    `_err.txt` files are left untouched".
  - The `result:` convention bullet's parenthetical about `cleanup.targets` —
    drop the `targets` mention; `result:` still controls section order.
  - Any remaining `error_suffix` reference — remove.
- `docs/architecture/overview.md`:
  - `CleanupConfig` table row → "`Cleanup` gate (`on`: success | always)".
  - `TranscriptionConfig` / `OllamaStepConfig` rows — drop `error_suffix`.
  - Cleanup / `--cleanup` prose — current outputs only; note pre-migration
    sidecars are an operator concern.
- `docs/architecture/decisions/` — short ADR: cleanup is not a migration tool;
  it removes only what the running version produces. Cross-reference
  ADR-005 ([[EPIC-049]]) and [[EPIC-051]].
- `deploy/prod/DEPLOY.md`, `deploy/prod-local/DEPLOY.md`: `--cleanup` section
  and any "Directory layout" mention of `_fix` / `_err.txt`; add an upgrade
  note that old sidecars are removed manually, not by `--cleanup`.

### 6. Tests

- `tests/test_config.py`: `CleanupConfig()` has no `targets`; `TranscriptionConfig()`
  / `OllamaStepConfig()` have no `error_suffix`; a YAML file that still sets
  `cleanup.targets` or `*.error_suffix` loads and logs the deprecation WARNING.
- `tests/test_cleanup_cli.py`: rewrite around the current layout —
  `--cleanup` removes `<file>.<ext>` and `_<dirname>.<ext>` (single- and
  multi-engine), removes stale `.md`/`.html` copies, empties the index; a
  pre-existing `meeting_fix.txt` / `meeting_err.txt` is **left in place**
  (explicit assertion of the new contract).
- `tests/test_pipeline_err_cleanup.py`: drop `CleanupConfig(targets=[])` and
  `error_suffix=` kwargs; the `test_disabled_index_falls_back_to_sidecar` case
  is already gone with [[EPIC-051]]. Keep the "failure → index row, no sidecar"
  assertions.
- `tests/test_rescan_cleans_formats.py`, `tests/test_output_format.py`:
  `clean_other_formats` new signature; still removes the stale-extension
  consolidated result.
- `tests/test_multi_engine.py`, `tests/test_processing_index.py`,
  `tests/test_processing_mode.py`, `tests/test_dry_run.py`: drop
  `CleanupConfig(targets=...)` / `error_suffix=` constructions.
- Grep the suite for `error_suffix` and `targets=` and clear every hit.

## Acceptance Criteria

- [x] `CleanupConfig` has only `on`; `TranscriptionConfig` and
  `OllamaStepConfig` have no `error_suffix`. Nothing in `src/` references
  either removed name.
- [x] An old config that still sets `cleanup.targets` or a section's
  `error_suffix` loads without error and logs one deprecation WARNING per key.
- [x] `whispercrawl --cleanup` removes `<file>.<ext>` / `<file>_<engine>.<ext>`
  and `_<dirname>.<ext>` / `_<dirname>_<engine>.<ext>` for the current
  `formatter.format`, removes stale-extension copies, and empties the
  processing index.
- [x] `whispercrawl --cleanup` does **not** remove `_fix` / `_sum` / `_all` /
  `_concat` / `*_err.txt` / `_diarize.json` files — they are left exactly as
  found.
- [x] `--once --cleanup` post-run behavior for the consolidated result is
  unchanged (still gated by `cleanup.on`).
- [x] `clean_other_formats` still clears a `.md`/`.html` result left by a prior
  `formatter.format` on a `rescan: true` run.
- [x] Config templates have no `error_suffix` lines and a `cleanup:` block with
  only `on:`.
- [x] Docs describe `--cleanup` as current-version-only and state that
  pre-upgrade sidecars are removed manually.
- [x] Full test suite green.

## Out of Scope

- **A migration command** to sweep pre-047/049 sidecars. Explicitly declined —
  `find <watch_dir> -name '*_fix.txt' -delete` (etc.) is the documented answer.
- **Touching the `<log_dir>/diarize/*.json` debug artifacts.** `--cleanup`
  stays within `watch_dir` result files; the diarize log tree is managed with
  the rest of `logs/`.
- **Removing `cleanup.on`** or the `--once --cleanup` post-run sweep. The
  success/always gate on the current result still has a use.
- **The legacy `<stem>_diarize.json` sidecar path in `transcriber.py`** (used
  only when `diarize_log` is on but no `log_dir` is set) — unrelated to
  cleanup config; left as-is.
- **Schema or index-format changes.** `state.clear()` is unchanged.
