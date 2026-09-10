# EPIC-061: Count Copied-In Files as Recent for `max_age_days`

## Goal

A file copied into `watch_dir` long after it was last modified must still be processed when `max_age_days` is set: the age window should treat "when this file arrived in the tree" as its age, not only "when its content was last modified".

## Problem Description

`max_age_days` (EPIC-039) excludes any file whose `st_mtime` is older than `now - max_age_days` days. Copying a file preserves its original modification timestamp — `cp -p`, `rsync -a`, robocopy, Windows Explorer, archive extraction all do this — while the *creation* time (Windows) or *inode-change* time (Linux) becomes the moment of the copy.

So the standard operator flow "copy an old recording into the watched directory for transcription" silently fails: the file's mtime is outside the window, `_candidate_stat` drops it at DEBUG level, and it is never transcribed — in a normal run, in `--refresh`, and in the per-directory result census (`directory_media_files`), which applies the same filter.

## Scope

### 1. `file_walker.py` — arrival-time comparison

- Add a module-level `_arrival_ts(st: os.stat_result) -> float` helper: the **newest** of `st_mtime`, `st_ctime` (creation time on Windows, inode-change time on Linux — both fresh after a copy), and `st_birthtime` when the platform exposes it.
- Add an `age_basis: str = "newest"` parameter to `_candidate_stat`, `iter_media_files`, and `directory_media_files`. The cutoff comparison becomes:
  - `"newest"` (default): compare `_arrival_ts(st)` against the cutoff — a copied-in old file is recent;
  - `"mtime"`: compare `st.st_mtime` — the pre-EPIC-061 strict behavior.
- The **newest-first sort key stays `st_mtime`** in both bases: priority among candidates remains "most recently modified first"; `age_basis` only decides membership in the window. (It also keeps ordering meaningful when a batch copy gives many files an identical arrival timestamp.)
- The processing-index identity (`mtime` + `size`) is untouched — a fresh ctime from a copy/rename must not invalidate stored transcripts.

### 2. `config.py` — `Config.age_basis`

- Add `age_basis: str = "newest"` to the top-level `Config` dataclass (beside `max_age_days`).
- Parse from `raw.get("age_basis", "newest")` in `load_config`; raise `ValueError` for any value other than `"mtime"` / `"newest"`.

### 3. `main.py`

- Pass `config.age_basis` to the `iter_media_files(...)` call in `_run_pipeline()` and to the `directory_media_files(...)` call in the per-directory census, keeping the two traversals consistent.

### 4. `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`

- Update the `max_age_days` comment (it no longer compares mtime only) and add a commented `# age_basis: newest` line documenting both values.

### 5. Tests — `tests/test_file_walker.py`

- `_arrival_ts` unit tests against synthetic stat objects (mtime newer / ctime newer / birthtime participates / absent birthtime).
- Newest basis (and the default): a file with a year-old mtime but fresh creation/ctime survives `max_age_days` — portable, because `os.utime` itself bumps ctime on Linux and the test-created file's creation time is "now" on Windows.
- `mtime` basis: the same file is excluded (strict behavior preserved).
- Newest basis with a faked old arrival time (monkeypatched `_arrival_ts`, since ctime cannot be set portably): the file is excluded.
- `directory_media_files` applies the same basis as `iter_media_files`.
- Existing mtime-window exclusion tests pin `age_basis="mtime"` explicitly (their fixtures are freshly created, so their arrival time is "now").

### 6. Tests — `tests/test_config.py`

- `age_basis` defaults to `"newest"` when absent from YAML.
- `age_basis: mtime` loads as `"mtime"`.
- Any other value raises `ValueError`.

## Acceptance Criteria

- With no config change, a file copied into `watch_dir` with an old mtime is picked up by a normal run (and by `--refresh` and the directory-result census) when `max_age_days` is set.
- `age_basis: mtime` restores the exact pre-EPIC-061 filtering for operators who want strict modification-time semantics.
- Processing order (newest-first by mtime) and the processing-index identity (mtime + size) are unchanged.
- All existing `file_walker`, `config`, and pipeline tests continue to pass.

## Out of Scope

- Changing the newest-first sort key or the index identity key.
- Per-directory or per-engine age overrides.
- Clamping/normalizing filesystem timestamps (network mounts with skewed clocks).
