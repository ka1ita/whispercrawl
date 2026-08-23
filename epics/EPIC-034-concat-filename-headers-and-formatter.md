# EPIC-034: Filename Headers in Concat and Formatter Pass for Concat File

## Goal

Two related improvements to the per-directory concat step:

1. **Filename headers** — prepend each file's text block in the concat output with a header line showing the source filename, so readers know where each block came from.
2. **Formatter pass for concat file** — run the concat file through the same Formatter step as every other output, so it is converted to `.md` / `.html` / `.txt` consistently.

## Scope

### Feature 1 — Filename headers in concat output

Currently `concat_transcriptions()` joins texts with `\n\n---\n\n` and loses the filename context.
After this change each block is preceded by a plain-text filename header:

```
filename_a.mp3

<transcript text>

---

filename_b.mp3

<transcript text>
```

The separator `---` stays between blocks (not after the last one).
Header format is plain text (no Markdown `#`); the Formatter already handles MD/HTML styling.

### Feature 2 — Formatter converts concat files

Currently `concat_path` is always written as `.txt` and is **not** added to `all_outputs_to_format`,
so it is never converted regardless of the active format.

After this change:
- `concat_path` is added to `all_outputs_to_format` after being written.
- `run_cleanup()` derives the concat file path with `output_path()` instead of hardcoding `.txt`.

## Acceptance Criteria

- Concat file contains one header line per source file (sorted filename order) above each text block.
- Concat file is converted to the active format (`.md`, `.html`, `.txt`) by the Formatter pass.
- `--cleanup` removes the concat file using the correct extension for the active format.
- All existing tests pass without modification (other than concat content assertions).

## Out of Scope

- Changing the separator string.
- Making the header format configurable (plain text only).
- Applying the formatter to `_err.txt` files.
