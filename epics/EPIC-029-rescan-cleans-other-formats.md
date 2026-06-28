# EPIC-029: rescan: true Cleans Output Files in Other Formats

## Goal

When `rescan: true`, the pipeline re-processes every media file and overwrites outputs in the
currently configured format. However, if the `formatter.format` was changed since the last run
(e.g. `txt` → `md`), outputs from the previous format (`.txt`, `.html`) are left as orphans
beside the new outputs. This EPIC removes those stale cross-format outputs whenever a file is
being reprocessed.

## Scope

- When `rescan: true` and a media file is about to be processed, delete all output files that:
  - share the same stem + a configured suffix label (`""`, `_fix`, `_sum`), AND
  - have a supported extension (`.txt`, `.md`, `.html`) that differs from the current format's extension.
- Error files (`_err.txt`) are always `.txt` and are NOT touched by this logic.
- The `_diarize.json` file is also excluded (it is not format-specific).
- When `rescan: false`, behavior is unchanged (EPIC-028 already handles skip logic).
- `--cleanup` is unchanged — it already uses the current format's extension exclusively.

## Acceptance Criteria

1. `rescan: true`, previous run was `txt`, current format is `md` → `<file>.txt`, `<file>_sum.txt`
   deleted before the new `.md` outputs are written.
2. `rescan: true`, previous run was `md`, current format is `html` → `<file>.md`, `<file>_sum.md`
   deleted.
3. `rescan: true`, previous run was `html`, current format is `txt` → `<file>.html`, `<file>_sum.html`
   deleted.
4. `rescan: true`, all outputs already in the current format → nothing extra deleted.
5. `rescan: false` → no change in behavior; other-format orphans left untouched.
6. Error files (`_err.txt`) and `_diarize.json` are never deleted by this logic.
7. Dry-run mode logs which files *would* be deleted without deleting them.

## Design Notes

- The list of suffixes to check comes from `cleanup.targets` (or the union of all configured
  `output_suffix` values) so it stays in sync with the pipeline configuration.
- All three supported extensions (`.txt`, `.md`, `.html`) are the exhaustive set; hardcode or
  derive from the validated allowlist in `config.py`.
- Implement as a helper on `Cleaner` (e.g. `clean_other_formats(file_path)`) called from
  `main.py` inside `run_pipeline()` at the start of each file, gated on `config.rescan`.
