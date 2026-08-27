# EPIC-039: Prioritize Newest Files and Bound Scan Age for Large Catalogs

## Goal

Make large catalogs (20,000+ files, mostly already processed) process newest content first, and let operators optionally bound processing to a recent time window so stale files stop being walked and stat-checked on every run.

## Problem Description

`iter_media_files` in `file_walker.py` walks the whole tree with `sorted(root.rglob("*"))` — alphabetical order, no awareness of file recency. In a catalog with tens of thousands of mostly-processed files:

- If a run is interrupted, time-boxed, or the backlog can't fully clear in one pass, files are picked up in directory/filename order rather than by what's newest — so old material can crowd out new material that operators actually care about first.
- Every run walks and stat-checks the entire tree, including files far outside any window of interest, with no way to bound that cost.

## Scope

### 1. `file_walker.py` — `iter_media_files`

- Add a `max_age_days: Optional[int] = None` parameter.
- Change the iteration to: filter as today (extension, skip marker, output-existence when not rescanning), plus a new age filter when `max_age_days` is set — skip files whose mtime is older than `now - max_age_days` days (log at DEBUG).
- Collect surviving candidates and yield them **sorted by mtime descending** (newest first) instead of alphabetically. Read `path.stat().st_mtime` once per candidate and reuse it for both the age filter and the sort key.

### 2. `config.py` — `Config`

- Add `max_age_days: Optional[int] = None` to the top-level `Config` dataclass; `None` means unbounded (current behavior). Parse from `raw.get("max_age_days")` in `load_config`; no validation needed beyond YAML's own int/null typing.

### 3. `main.py`

- Pass `config.max_age_days` to the `iter_media_files(...)` call in `run_pipeline()`.

### 4. `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`

- Add a commented `# max_age_days: 180` line near `skip_marker`/`rescan`, with a comment explaining it bounds the scan to recent files (null/omitted = unbounded).

### 5. Tests — `tests/test_file_walker.py`

- Files with different mtimes (set via `os.utime`) → yielded newest-first.
- `max_age_days` set, file older than the window → excluded.
- `max_age_days` set, file within the window → included.
- `max_age_days: None` (default/omitted) → no age filtering, existing behavior unchanged.
- Age filter combines correctly with `rescan`, `skip_marker`, and output-existence checks (order of precedence: skip marker → age → output-existence).

### 6. Tests — `tests/test_config.py` (or wherever `Config`/`load_config` is tested)

- `max_age_days` defaults to `None` when absent from YAML.
- `max_age_days: 180` in YAML loads as `180` on `Config`.

## Acceptance Criteria

- With no config change, behavior is unchanged except that files are now processed newest-first instead of alphabetically.
- `max_age_days` defaults to unbounded (`None`); setting it excludes files older than the window from both dry-run and real runs.
- All existing `file_walker`, `config`, and pipeline tests continue to pass.

## Out of Scope

- Any persisted index/cache to avoid re-walking the filesystem tree (the walk itself is still O(n) per run).
- Per-directory or per-extension age overrides.
- Changing how directory summarization batches or orders files.
