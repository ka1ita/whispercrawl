# EPIC-031: Skip Files Containing a Configurable Marker in Their Name

## Goal

Allow operators to permanently exclude individual audio/video files from processing by placing a configurable text marker (default `_skip`) anywhere in the filename. The check is applied in `iter_media_files` before any output-existence logic.

## Problem Description

Currently there is no lightweight way to permanently exclude a single file without removing it from the watch directory. The only option is `rescan: false` plus a pre-existing output file, which is fragile and requires creating placeholder files.

A simple naming convention — e.g. rename `interview.mp3` to `interview_skip.mp3` — lets operators exclude files with a single rename, without touching config or output directories.

## Scope

### 1. `config.py` — `Config`

Add a `skip_marker: str = "_skip"` field to the top-level `Config` dataclass. An empty string disables the feature.

### 2. `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`

Add a commented `skip_marker: _skip` line under the top-level config block, adjacent to `rescan`.

### 3. `file_walker.py` — `iter_media_files`

Add a `skip_marker: str = ""` parameter. Before the rescan/output-existence check, test whether `skip_marker` is non-empty and is present in `path.stem` (case-insensitive). If so, log at DEBUG level and skip the file.

```python
if skip_marker and skip_marker.lower() in path.stem.lower():
    # log debug: skipping <path> — filename contains skip marker
    continue
```

### 4. `main.py`

Pass `config.skip_marker` to `iter_media_files` when calling it in `run_pipeline()` and `run_dry_run()`.

### 5. Tests — `tests/test_file_walker.py`

- Filename contains `_skip` → file not yielded (marker present, default config).
- Filename contains `_SKIP` (upper-case) → file not yielded (case-insensitive).
- Marker in the middle of the stem (`my_skip_recording.mp3`) → file not yielded.
- `skip_marker: ""` (disabled) → file with `_skip` in name is yielded normally.
- File without marker → yielded as normal (no regression).
- `skip_marker` check takes priority over output-existence check (file is skipped even when no output exists).

## Acceptance Criteria

- `skip_marker` config field defaults to `"_skip"`; an empty string disables the feature.
- Any file whose stem contains the marker string (case-insensitive) is skipped and never passed to the pipeline.
- Skipped files are logged at DEBUG level with a clear message.
- `--dry-run` respects the marker (files with the marker do not appear in the dry-run file list).
- All existing `file_walker` and pipeline tests continue to pass.

## Out of Scope

- Marker matching on directory names.
- Multiple skip markers.
- Wildcard or regex marker patterns.
