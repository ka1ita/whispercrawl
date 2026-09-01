# EPIC-043: Relocate the Processing Index to a Dedicated `db/` Directory

## Goal

Move the persisted processing index (`state.db`) out of the watched media tree
(`<watch_dir>/.whispercrawl/state.db`) and into a dedicated `db/` directory
anchored at the **script/config root** — the directory containing `config.yaml`.

- Local run (`whispercrawl --config config.yaml`): `./db/state.db`.
- Container run (config bind-mounted at `/config.yaml`): `/db/state.db`, backed by
  its own `./db` bind mount alongside `./audio` and `./logs`.

An explicit `state.path` in config still overrides the default and is unchanged.

## Problem Description

`state.db` (plus its `-wal`/`-shm` siblings) currently lives inside the directory
being scanned ([`state.py:191`](../src/whispercrawl/state.py#L191),
`default_state_path(watch_dir) -> <watch_dir>/.whispercrawl/state.db`). This has
drawbacks:

- **It pollutes the media tree.** Operators back up, sync, or hand `audio/` to
  other tools; a SQLite DB with live WAL files inside it is surprising and easy to
  copy into a backup half-written. `file_walker` has to defensively exclude
  `.whispercrawl/` from every `rglob` ([`file_walker.py:49`](../src/whispercrawl/file_walker.py#L49)),
  and `run_cleanup`'s `rglob("*")` scans step around it too.
- **The media mount is often read-mostly or read-only.** When `audio/` is an NFS
  export or a `:ro`-intended share, the service can't create `.whispercrawl/`.
  A separate `db/` mount can be writable without making the whole media tree
  writable.
- **`.whispercrawl/` is a hidden dot-dir buried one level under `watch_dir`.**
  A dedicated top-level `db/` beside `audio/` and `logs/` is where an operator
  expects mutable service state to live, matching how `logs/` already works.

The index is safe to delete and rebuilds itself from existing output files with no
reprocessing (EPIC-040), so relocating it is low-risk — but a large catalog would
pay one slow "rediscovery" run if the old DB were simply orphaned. This epic
therefore also does a one-time automatic move of a legacy DB to the new location.

## Scope

### 1. `state.py`

- Rename the location constant: `STATE_DIRNAME = "db"` (was `".whispercrawl"`).
  Add `LEGACY_STATE_DIRNAME = ".whispercrawl"` for traversal exclusion and the
  migration probe below. `STATE_FILENAME` stays `"state.db"`.
- Change `default_state_path` to anchor at the **config root**, not `watch_dir`:

  ```python
  def default_state_path(config_root: Union[str, Path]) -> str:
      return str(Path(config_root) / STATE_DIRNAME / STATE_FILENAME)
  ```

  `config_root` is the directory containing the config file.
- `open_state(enabled, path, config_root, watch_dir)` — add a `config_root`
  parameter; keep `watch_dir` only for the legacy probe:
  - Resolve `resolved = Path(path) if path else Path(default_state_path(config_root))`.
  - **One-time migration:** when `resolved` does not exist but the legacy path
    `Path(watch_dir) / LEGACY_STATE_DIRNAME / STATE_FILENAME` does, create
    `resolved.parent`, then move `state.db` and any `state.db-wal` / `state.db-shm`
    siblings to `resolved.parent` (`shutil.move`, best-effort inside a
    `try/except` that logs a WARNING and falls through to a fresh DB on failure).
    Log at INFO: `Migrated processing index: <old> -> <resolved>`. Remove the now
    empty legacy `.whispercrawl/` dir if empty.
  - Then `ProcessingState.open(resolved)` as today.

### 2. `config.py`

- `load_config(path)` already knows the config file path. Resolve the default:

  ```python
  state_cfg = _build(StateConfig, raw.get("state", {}) or {})
  if state_cfg.path is None:
      from whispercrawl.state import default_state_path
      state_cfg.path = default_state_path(Path(path).resolve().parent)
  ```

- `StateConfig.path` docstring/comment updated: `# default: <config dir>/db/state.db`.
- `${STATE_DIR:...}` style expansion in an explicit `path:` still works unchanged
  (`_expand_env` runs over the whole file before parsing).

### 3. `main.py`

- `run_pipeline()` / `_run_pipeline()`: pass the config-file directory into
  `open_state`. The config path is available where `load_config` is called
  ([`main.py`](../src/whispercrawl/main.py) CLI entry) — thread it onto `Config`
  as a non-serialized attribute **or** re-derive it in `run_pipeline` from the
  already-resolved `config.state.path` parent. Prefer the latter (no `Config`
  change): `config.state.path` is always populated by `load_config`, so
  `open_state(config.state.enabled, config.state.path, ..., config.watch_dir)` is
  enough and the `config_root` arg is only needed for the `path is None` case,
  which `load_config` has already resolved. Net effect: `open_state` can drop
  `config_root` and take `(enabled, path, watch_dir)` where `path` is always set
  by the time `main.py` calls it.
- `run_cleanup()` ([`main.py:120`](../src/whispercrawl/main.py#L120)): replace the
  `default_state_path(config.watch_dir)` fallback with `config.state.path`
  directly (always resolved by `load_config`). Clearing behavior unchanged.

### 4. `file_walker.py`

- Exclude **both** `STATE_DIRNAME` (`"db"`) and `LEGACY_STATE_DIRNAME`
  (`".whispercrawl"`) from `rglob` traversal ([`file_walker.py:49`](../src/whispercrawl/file_walker.py#L49)):
  `if STATE_DIRNAME in path.parts or LEGACY_STATE_DIRNAME in path.parts: continue`.
  Defensive only — the default DB now lives outside `watch_dir` — but covers an
  operator who points `state.path` back inside the media tree, and covers a
  not-yet-migrated legacy dir on the first post-upgrade run.

### 5. `Dockerfile`

- Add `/db` to the `VOLUME` list: `VOLUME ["/audio", "/logs", "/db"]`.

### 6. `deploy/prod/docker-compose.prod.yml`, `deploy/prod-local/docker-compose.prod-local.yml`

- Add a `db` bind mount to the `whispercrawl` service, same relabel suffix as the
  siblings: `- ./db:/db:Z` (prod) and `- ./db:/db:Z` (prod-local).
- No new env var needed: config is mounted at `/config.yaml`, so the resolved
  default is `/db/state.db`.

### 7. `deploy/dev/docker-compose.dev.yml`

- Add `- ../../db:/db` to the `whispercrawl` service volumes (no `:Z` — dev host).

### 8. `deploy/prod/setup.sh`, `deploy/prod-local/setup.sh`

- `mkdir -p audio logs db` and `chmod 750 audio logs db`.
- Root branch: `chown -R "$APP_UID:$APP_GID" audio logs db`.
- Non-root branch: add `db` to the printed `sudo chown -R ... "$INSTALL_DIR/audio"
  "$INSTALL_DIR/logs"` line so it becomes `... "$INSTALL_DIR/audio"
  "$INSTALL_DIR/logs" "$INSTALL_DIR/db"`.

### 9. `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`

Update the commented `state.path` hint:

```yaml
state:
  enabled: true
  # path: ./db/state.db     # default: <config dir>/db/state.db
```

(`deploy/prod` and `deploy/prod-local`: `# path: /db/state.db`.)

### 10. `.gitignore`

- Add `/db/` and `deploy/*/db/` (keep the existing `**/.whispercrawl/` line so a
  pre-migration legacy dir still stays untracked).

### 11. Documentation

- `docs/architecture/overview.md` — `state.py` section
  ([`overview.md:33`](../docs/architecture/overview.md#L33)): new default location
  `<config dir>/db/state.db`; note the one-time automatic migration from
  `<watch_dir>/.whispercrawl/state.db`; update the `file_walker` note about the
  excluded directory name.
- `CLAUDE.md` "Key Conventions": update the **Persisted index** bullet's path from
  `<watch_dir>/.whispercrawl/state.db` to `<config dir>/db/state.db` (and the
  Docker `/db` mount).
- `deploy/prod/DEPLOY.md`, `deploy/prod-local/DEPLOY.md`: "Processing index"
  section and the "Directory layout" tree — `db/state.db` instead of
  `audio/.whispercrawl/state.db`; add `db/` to the mount list and to `setup.sh`'s
  created dirs; note the auto-migration on first upgrade run.

### 12. Tests

- `tests/test_state.py`:
  - `default_state_path("/some/root")` → `/some/root/db/state.db`.
  - `open_state`: legacy `<watch_dir>/.whispercrawl/state.db` present, new path
    absent → DB (and `-wal`/`-shm` if present) moved to `<config_root>/db/`;
    records preserved (`lookup` of a pre-seeded row still works after migration);
    empty legacy dir removed.
  - `open_state`: new path already exists → legacy DB left untouched, no move.
  - `open_state`: neither exists → fresh DB created at the new path, no error.
  - `open_state`: migration `shutil.move` raises → WARNING logged, fresh DB at new
    path, run continues.
- `tests/test_config.py`:
  - `state.path` default now resolves to `<config-file dir>/db/state.db` (anchored
    at the config file's directory, **not** `watch_dir`) — e.g. load a config from
    a tmp dir with `watch_dir` pointing elsewhere and assert the resolved path.
  - Explicit `state.path` in the YAML is still respected verbatim.
- `tests/test_file_walker.py`:
  - A `db/` directory under `watch_dir` containing a `state.db` is skipped by
    traversal (no attempt to treat it as media, not yielded).
  - A legacy `.whispercrawl/` directory under `watch_dir` is still skipped
    (regression).
- `tests/test_main.py` (or wherever `run_cleanup` is covered): `--cleanup` clears
  the index at the new `db/state.db` location.
- Pipeline/integration: a run started with a legacy `.whispercrawl/state.db`
  (seeded with some `done` rows) reprocesses nothing — the rows are migrated and
  honored at the new location.

## Acceptance Criteria

- [x] With no `state.path` set, the index is created at `<config dir>/db/state.db`
      (local) / `/db/state.db` (container).
- [x] An explicit `state.path` still overrides the default and is used verbatim.
- [x] On first run after upgrade, an existing `<watch_dir>/.whispercrawl/state.db`
      (with `-wal`/`-shm`) is moved to the new `db/` location automatically, with
      all records intact and zero reprocessing; the empty legacy dir is removed.
- [x] If migration fails, the run logs a WARNING and continues with a fresh index
      (rebuilt from output files, no reprocessing).
- [x] `file_walker` never descends into `db/` or `.whispercrawl/` under
      `watch_dir`.
- [x] `docker-compose.prod.yml`, `docker-compose.prod-local.yml`, and
      `docker-compose.dev.yml` mount a dedicated `db/` directory; `setup.sh`
      creates and `chown`s it.
- [x] `--cleanup` clears the index at its new location.
- [x] `state.enabled: false` still creates nothing.
- [x] All existing tests pass; docs and config templates reflect the new path.

## Out of Scope

- Changing the index schema, contents, or the `done`/`error`/`partial` +
  per-step tracking semantics (EPIC-040 / EPIC-041) — only the file location moves.
- Supporting multiple watch dirs sharing one index, or one index per watch dir —
  still exactly one index per config.
- Removing the legacy `**/.whispercrawl/` `.gitignore` entry or the
  `LEGACY_STATE_DIRNAME` constant — both stay for backward compatibility with
  un-migrated deployments.
- A config-schema version bump or any migration for an explicit `state.path` that
  already points at `.whispercrawl/` — an operator override is left as-is.
