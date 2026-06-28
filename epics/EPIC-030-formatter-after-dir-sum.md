# EPIC-030: Run Formatter After Directory Summarization

## Goal

Fix a bug where directory summarization fails with "No summary files found" when a
non-txt output format is configured. The formatter currently runs per-file immediately
after each file's pipeline steps, converting `_sum.txt` → `_sum.md`/`.html` and
deleting the `.txt` source. When directory summarization runs afterwards, it globs for
`*_sum.txt` — which no longer exist — and raises a `SummarizationError`.

Move the formatter to the final step so it runs after **all** pipeline steps including
directory summarization. All intermediate steps (transcription, post-processing, file
summarization, directory summarization) always read and write plain `.txt` files.
Formatted output is produced once at the very end.

## Scope

- `main.py` — defer `formatter.format_file()` calls:
  - Collect per-file output paths in `files_to_format` but do **not** call
    `formatter.format_file()` inside the per-file loop.
  - After the dir-summarization loop, format all collected per-file paths.
  - Include dir summary paths in the same final formatting pass.
- `pipeline/summarizer.py` — `summarize_directory` already globs `*{suffix}.txt`;
  no change needed there. Verify it stays correct.
- No config changes required.

## Acceptance Criteria

1. When `formatter.format` is `md` or `html`, directory summarization succeeds and
   produces a formatted dir summary file.
2. After the final formatting pass, no orphan `.txt` files remain for the per-file
   outputs that were converted (same behaviour as before for the non-dir case).
3. When `formatter.format` is `txt`, behaviour is unchanged (no-op formatter, `.txt`
   files written as before).
4. When `formatter.enabled` is `false`, behaviour is unchanged (no format conversion).
5. Existing tests pass. New tests cover the failing scenario:
   - `format: md`, file summarization enabled, dir summarization enabled → dir
     summary succeeds and is written as `.md`; no `_sum.txt` orphan files.
   - `format: html`, same conditions → dir summary written as `.html`.
   - `format: txt` → all outputs remain `.txt`; dir summary succeeds as before.
