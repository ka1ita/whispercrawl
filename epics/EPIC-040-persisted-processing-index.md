# EPIC-040: Persisted Processing Index and Per-Run File Cap for Large Catalogs

## Goal

Stop re-probing the filesystem for work that is already done. Give `whispercrawl` a small persisted index of what it has processed so a scheduled run over a 20,000+ file catalog does a dict lookup instead of up to three `exists()` syscalls per file, resumes cleanly after an interrupted run, and can be bounded to a fixed number of files per invocation without losing progress.

## Problem Description

EPIC-039 made large catalogs process newest-first and added `max_age_days`, but its "Out of Scope" section deferred the actual cost driver:

> Any persisted index/cache to avoid re-walking the filesystem tree (the walk itself is still O(n) per run).

For a catalog that is mostly already processed, every scheduled tick still pays:

- `root.rglob("*")` yields **every** entry in the tree — media files plus the `_fix` / `_sum` / `_all` / `_diarize.json` outputs beside them (often 3–4× the media count).
- `path.stat()` on every media file (age filter + mtime sort key).
- Up to **three `path.with_name(...).exists()` syscalls per media file that has no matching output** ([`file_walker.py:52`](../src/whispercrawl/file_walker.py#L52)), just to conclude "already processed, skip".

On RedOS 8 with SELinux `:Z` bind mounts and possibly network-backed storage, that is a syscall storm on every interval to discover that nothing new arrived. `max_age_days` only helps operators willing to permanently stop looking at older files.

Two related weaknesses:

- **No durable progress.** A first run over a 20k backlog runs until it finishes or crashes. If it dies at file 15,000, the directory-summarization pass never runs, so no directory gets a `_all` / `_sum`, and the next run re-derives "what's left" purely from which output files happen to exist.
- **Unbounded memory.** `dir_file_texts` in [`main.py:176`](../src/whispercrawl/main.py#L176) accumulates every transcript **and** every post-processed text for the entire run and is never freed per-directory — 20k transcripts resident before the summary pass starts.

## Scope

### 1. New module — `src/whispercrawl/state.py`

- A `ProcessingState` class wrapping a single SQLite file (stdlib `sqlite3`, WAL mode, no new dependency).
- Schema:
  - `files(path TEXT PRIMARY KEY, mtime REAL, size INTEGER, status TEXT, updated_at REAL, detail TEXT)` — `status` ∈ `done` | `error` | `partial`. `path` stored relative to `watch_dir`.
  - `meta(key TEXT PRIMARY KEY, value TEXT)` — schema version, `watch_dir` fingerprint.
- API:
  - `ProcessingState.open(path) -> ProcessingState` (creates + migrates schema); usable as a context manager.
  - `lookup(rel_path) -> Optional[Record]`.
  - `is_current(rel_path, mtime, size) -> bool` — `True` only when a `done` record exists with matching `mtime` **and** `size`.
  - `mark(rel_path, status, mtime, size, detail="")` — upsert.
  - `forget(rel_path)` / `clear()` — for `--cleanup`.
- No-op / null-object variant (`NullState`) so callers never branch on `None`.

### 2. `config.py` — `Config`

- Add a `StateConfig` dataclass:
  - `enabled: bool = True`
  - `path: Optional[str] = None` — default resolved at load time to `<watch_dir>/.whispercrawl/state.db`.
- Add `state: StateConfig = field(default_factory=StateConfig)` to `Config`; parse from `raw.get("state", {})` via `_build`.
- Add `max_files_per_run: Optional[int] = None` to `Config` (top level, beside `max_age_days`); `None` = unlimited. Parse from `raw.get("max_files_per_run")`; `load_config` raises `ValueError` if set and `< 1`.

### 3. `file_walker.py` — `iter_media_files`

- Add a `state: ProcessingState | NullState | None = None` parameter (default `None` → today's behavior exactly).
- Per candidate, after the extension / skip-marker / age filters:
  - When `rescan` is `False` **and** a state is supplied: if `state.is_current(rel_path, mtime, size)` → skip with no `exists()` probes.
  - If the file is **not** in the index (or stale), fall back to the existing multi-extension output-existence check. When that check finds outputs, call `state.mark(rel_path, "done", mtime, size)` and skip — this back-fills the index for a pre-existing catalog on the first indexed run, with **no reprocessing**.
- Age filter, skip-marker, and sort behavior are unchanged. Precedence: skip marker → age → state lookup → output-existence fallback.
- `rescan: True` bypasses all state/output checks (reprocess everything) but the run still updates the index afterward.

### 4. `main.py`

- `run_pipeline()`:
  - Open the state store (or `NullState` when `config.state.enabled` is `False`) in a `with` block around the run; pass it to `iter_media_files(...)`.
  - Apply `config.max_files_per_run` as a slice of the pending list **after** the newest-first sort. Log `processing N of M pending files; K remain for the next run` when the cap truncates.
  - After each file: `state.mark(rel, "done", mtime, size)` on full success; `"error"` with the message in `detail` on any step failure; `"partial"` if the file was interrupted mid-pipeline (best-effort, e.g. `KeyboardInterrupt` / `finally`).
  - Free each directory's entry (`del dir_file_texts[dir_path]`) immediately after its summary/concat is written, so peak memory is bounded by one directory (or by `max_files_per_run`).
- `run_dry_run()` path: pass the state through so `--dry-run` reflects what a real run would skip; never writes to the store.
- `run_cleanup()`: after deleting output files (non-dry-run), call `state.clear()` (or `forget` per affected file) so a subsequent run reprocesses. Dry-run leaves the store untouched and logs that it would be cleared.

### 5. `file_walker.py` / walker exclusions

- Exclude the state directory (`.whispercrawl/`) from `rglob` results defensively (it holds no media extensions today, but a dot-dir keeps it out of any future globbing and out of `run_cleanup`'s `rglob("*")` scans).

### 6. `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`

- Add near `max_age_days`:
  ```yaml
  # Persisted index of processed files — avoids re-checking the whole tree every run.
  state:
    enabled: true
    # path: ./audio/.whispercrawl/state.db   # default: <watch_dir>/.whispercrawl/state.db

  # Max files to process per run; the rest are picked up on the next scheduled run. omit/null = unlimited
  # max_files_per_run: 500
  ```

### 7. Documentation

- `docs/architecture/overview.md`: note the state store, its location, and that deleting it forces a full re-derivation from output files (not reprocessing) on the next run.
- `deploy/prod/DEPLOY.md`, `deploy/prod-local/DEPLOY.md`: mention `state.db` lives under `audio/.whispercrawl/`, is safe to delete, and should be included in (or deliberately excluded from) backups.
- `CLAUDE.md` "Key Conventions": add a line on the persisted index and `max_files_per_run`.

### 8. Tests

- `tests/test_state.py` (new): open/migrate; `mark` then `lookup`; `is_current` true only on matching mtime **and** size; stale mtime → not current; `clear` / `forget`; context-manager close; `NullState` returns "not current" for everything and swallows `mark`.
- `tests/test_file_walker.py`:
  - Indexed `done` file with unchanged mtime/size → skipped with **zero** `exists()` calls (assert via `monkeypatch` counter or `mock` on `Path.exists`).
  - Indexed file whose mtime changed → re-queued.
  - Un-indexed file **with** existing outputs → skipped **and** recorded `done` in the state (back-fill).
  - Un-indexed file with no outputs → queued.
  - `rescan: True` → indexed `done` files still yielded.
  - `state=None` → behavior identical to pre-epic (regression).
  - Age / skip-marker filters still apply ahead of the state check.
- `tests/test_config.py`: `state` defaults (`enabled=True`, `path=None` → resolved default); `max_files_per_run` defaults to `None`; `max_files_per_run: 0` → `ValueError`.
- Pipeline/integration:
  - Run over N files with `max_files_per_run=k` → exactly `k` processed, `k` `done` records, `N-k` still pending; second run processes the remainder.
  - Interrupted run (simulate failure on file 3 of 5) → files 1–2 `done`, file 3 `error`, 4–5 pending; rerun completes 3–5 without touching 1–2.
  - `--cleanup` removes outputs **and** empties the state; next run reprocesses.
  - `state.enabled: false` → no `state.db` created, behavior matches EPIC-039.

## Acceptance Criteria

- [x] With `state.enabled: true` and an already-processed catalog, a scheduled run performs no per-file `exists()` probing for indexed files — confirmed by test.
- [x] First indexed run over a pre-existing catalog reprocesses nothing; it back-fills `done` records from existing output files.
- [x] `max_files_per_run` bounds a single run; remaining files are processed on subsequent scheduled runs with no lost or duplicated work.
- [x] An interrupted run resumes from the state store; completed files are not reprocessed.
- [x] `--cleanup` clears the state store (non-dry-run only).
- [x] `dir_file_texts` peak memory is bounded by one directory (or by `max_files_per_run`), not the whole run.
- [x] `state.enabled: false` reproduces EPIC-039 behavior exactly; `state=None` default keeps `iter_media_files` backward-compatible.
- [x] All existing `file_walker`, `config`, `main`, and pipeline tests pass.

## Out of Scope

- Filesystem-event watching (inotify / `watchdog`) to skip the O(n) `rglob` walk entirely — the walk still happens once per run; this epic only removes the per-file probing and reprocessing decisions on top of it.
- Directory-mtime short-circuiting (skip `stat()`-ing files in directories whose mtime is unchanged) — a reasonable phase-2 optimization once the index exists.
- Concurrent / multi-process runs against one state store (APScheduler runs a single job instance; WAL mode is defensive only).
- Migrating the service-request `.ndjson` log or diarization JSON into the store.
- Any change to how directory summarization batches or orders files, or to the fact that a directory's `_all` concat only contains files touched in the current run.
