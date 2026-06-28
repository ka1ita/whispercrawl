# EPIC-027: Cleanup and Skip-Check Use Format Extension for MD and HTML

## Goal

`--cleanup` and the per-file pipeline cleanup must delete files with the correct extension for the active output format. Likewise, the skip-processed check in `iter_media_files` must look for the right extension so files are not re-processed when their output already exists as `.md` or `.html`.

Currently three places use the pattern `".html" if fmt == "html" else ".txt"`, which silently falls back to `.txt` for `"md"` format. This means:

- `--cleanup` with `format: md` looks for `.txt` files that no longer exist (the formatter converted them to `.md` and deleted the `.txt`), so nothing is cleaned.
- `Cleaner` (per-file cleanup inside the pipeline) has the same blind spot.
- `iter_media_files` (skip-processed check) looks for `.txt` even when format is `md`, so already-processed files get re-processed on every run.

Error files are always written as `.txt` regardless of format — that behaviour is correct and must not change.

## Scope

Three code changes, all mechanical:

1. **`main.py` — `output_path()` helper** (line 28–30):  
   Add `elif fmt == "md": ext = ".md"` so the helper returns the right path for all three formats.

2. **`pipeline/cleaner.py` — `Cleaner.__init__`** (line 14):  
   Mirror the same fix: `".md" if output_format == "md" else ".html" if output_format == "html" else ".txt"`.

3. **`file_walker.py` — `iter_media_files`** (line 27):  
   Same fix: derive `ext` from all three possible values of `output_format`.

## Acceptance Criteria

- `--cleanup` with `format: md` removes `<stem><suffix>.md` files; no `.txt` files are touched.
- `--cleanup` with `format: html` removes `<stem><suffix>.html` files (existing behaviour, must not regress).
- `--cleanup` with `format: txt` removes `<stem><suffix>.txt` files (existing behaviour, must not regress).
- Error files (`_err.txt`) are always removed by `--cleanup` regardless of format (existing behaviour).
- Per-file `Cleaner` removes `.md` files when format is `md`.
- `iter_media_files` skips a file when `<stem><transcription_suffix>.md` already exists and format is `md`.
- All existing cleanup and file-walker tests continue to pass.
- New tests cover the `md` case for `run_cleanup`, `Cleaner`, and `iter_media_files`.
