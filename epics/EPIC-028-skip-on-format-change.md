# EPIC-028: Skip Files Whose Output Exists in a Different Format

## Goal

When the configured `output.format` changes between runs (e.g. from `txt` to `md`, or from `html` to `txt`), the service must still recognise that a file was already processed and skip it — unless `rescan: true` is set.

Currently `iter_media_files` only checks for an output file whose extension matches the *current* format. If the format was changed after the first run, none of the old output files match, so every file is re-processed even though it already has a transcript.

## Problem Description

Suppose a directory was processed with `format: txt`, producing `recording_fix.txt` for each file. The operator then changes the config to `format: md`. On the next run, `iter_media_files` looks for `recording_fix.md`, finds nothing, and queues every file for re-processing — triggering expensive transcription calls unnecessarily.

The same problem exists in reverse: switching from `md` back to `txt` would re-process all files that already have `_fix.md` outputs.

The correct behaviour: if *any* recognised output extension (`_fix.txt`, `_fix.md`, `_fix.html` — same stem, any supported format) already exists beside the source file, the file is considered processed and should be skipped.

`rescan: true` overrides this: when set, files are always re-processed regardless of what already exists (current behaviour is preserved).

## Scope

### 1. `file_walker.py` — `iter_media_files`

Replace the single-extension skip check with a multi-extension check.

Current logic (after EPIC-027 fix):
```python
ext = ".md" if output_format == "md" else ".html" if output_format == "html" else ".txt"
skip_path = base / f"{stem}{transcription_suffix}{ext}"
if not rescan and skip_path.exists():
    ...skip...
```

New logic:
```python
if not rescan:
    all_exts = (".txt", ".md", ".html")
    if any((base / f"{stem}{transcription_suffix}{e}").exists() for e in all_exts):
        ...skip...
```

The transcription suffix (`_fix` or similar) is already extracted from config — no interface change needed.

### 2. Tests — `tests/test_file_walker.py`

Add parametrised cases covering:
- File processed with `txt` format, config now set to `md` → file skipped.
- File processed with `md` format, config now set to `html` → file skipped.
- File processed with `html` format, config now set to `txt` → file skipped.
- `rescan: true` with existing cross-format output → file is NOT skipped (re-processed).
- No output file in any format → file is queued (existing behaviour, must not regress).

## Acceptance Criteria

- A source file is skipped when an output file with the same stem and any supported format extension (`_fix.txt`, `_fix.md`, `_fix.html`) exists beside it, regardless of the currently configured format.
- `rescan: true` bypasses the check entirely — all files are re-queued.
- Existing skip behaviour (same-format output exists) is preserved.
- All existing `file_walker` tests continue to pass.
- New parametrised tests cover all cross-format combinations.

## Out of Scope

- Converting or migrating existing output files when the format changes.
- `--cleanup` behaviour (separate concern, covered by EPIC-027).
- Directory summary skip logic (directory-level outputs are not affected by this issue).
