# EPIC-033: Per-Directory Concatenation of Transcriptions

## Goal

Replace the current per-directory summarization stage (which collected per-file
`_sum.txt` outputs and LLM-summarized them) with a two-sub-step process:

1. **Concatenate** all transcription files in the directory into a single combined
   file.  This file is written to disk beside the other outputs.
2. **LLM-summarize** that combined file (same ollama call as today, but now the
   input is the full concatenated transcriptions, not a collection of summaries).

## Context

Currently `summarize_directory()` in `summarizer.py` globs `*_sum.txt` files and
feeds them to the LLM.  That means the LLM only sees per-file summaries, not the
raw transcription text.  The new approach exposes the full, ordered transcription
content to the LLM, which yields a higher-fidelity directory-level result.

An underscore-prefix option is added so both the combined and summary files sort
to the top of the directory listing (before regular audio/transcript files).

## New Config Fields (`dir_summarization`)

```yaml
dir_summarization:
  llm_enabled: true
  concat_source: postprocessed   # "postprocessed" (_fix / replaced transcript) | "original" (raw transcript)
  underscore_prefix: false       # true → output files named _<dirname>_sum.<ext>; false → <dirname>_sum.<ext>
  concat_suffix: _concat         # suffix label for the combined transcriptions file (written as .txt always)
  # remaining fields unchanged
  url: ...
  model: ...
  prompt: ...
  output_suffix: _sum
  error_suffix: _err
  timeout: 300
```

`concat_source` mirrors `file_summarization.summarize_source` — it selects which
per-file text is concatenated:
- `"postprocessed"` — use the post-processed text when available; fall back to the
  raw transcript for files where post-processing was skipped or failed.
- `"original"` — always use the raw transcript.

`underscore_prefix` — when `true`, prepend `_` to the directory name in output
filenames:
- combined file: `_<dirname><concat_suffix>.txt`
- LLM summary: `_<dirname><output_suffix>.<ext>`

`concat_suffix` — suffix label for the combined transcriptions file.  The file is
always written as plain `.txt` (it is raw, unformatted content — not passed through
the Formatter).  Add it to `cleanup.targets` if automatic cleanup is desired.

## Scope

### `config.py`

- Add `concat_source: str = "postprocessed"` to `DirSummarizationConfig`.
- Add `underscore_prefix: bool = False` to `DirSummarizationConfig`.
- Add `concat_suffix: str = "_concat"` to `DirSummarizationConfig`.
- Validate `concat_source` in `load_config` (must be `"postprocessed"` or
  `"original"`).

### `pipeline/summarizer.py`

- Replace `summarize_directory(dir_path, file_sum_suffix)` with two methods:
  - `concat_transcriptions(dir_path, transcript_suffix, fix_suffix, concat_source) -> str`
    — collects the per-file transcription texts (in sorted filename order) and
    joins them with a `\n\n---\n\n` separator; raises `SummarizationError` if no
    files found.
  - `summarize_text(text, label) -> str`
    — thin wrapper around `_call_ollama(text, file=label)` (replaces both
    `summarize_file` and `summarize_directory`; `summarize_file` becomes an alias
    or is removed if unused).

### `main.py`

Replace the current `dir_summarizer.summarize_directory(...)` call with:

1. Call `dir_summarizer.concat_transcriptions(...)` to concatenate; write result to
   `<underscore_prefix><dirname><concat_suffix>.txt` (always plain `.txt`).
2. If `dir_summarization.llm_enabled`, call `dir_summarizer.summarize_text(combined, label)`;
   write result via `output_path(dir_base_with_prefix, output_suffix, fmt)` and
   add to `all_outputs_to_format`.

Derive `dir_base_with_prefix` based on `underscore_prefix`:
```python
prefix = "_" if config.dir_summarization.underscore_prefix else ""
dir_base = dir_path / (prefix + dir_path.name)
```

Per-file transcription text must be passed through the pipeline and collected in
a dict keyed by `file_path`, so `concat_transcriptions` can access the in-memory
text rather than re-reading files from disk.  This avoids issues with
`replace_transcription: true` (which overwrites the `.txt` before the dir stage).

### `config.yaml` (and prod / prod-local variants)

- Add `concat_source: postprocessed` under `dir_summarization`.
- Add commented `underscore_prefix: false` under `dir_summarization`.
- Add commented `concat_suffix: _concat` under `dir_summarization`.
- Update the `dir_summarization` prompt to reflect that input is now full
  transcriptions, not summaries.

### Cleanup

- `run_cleanup` in `main.py`: derive `dir_base` using the same prefix logic so the
  concat and summary files are found and deleted correctly.
- The `concat_suffix` target must be added manually to `cleanup.targets` by the
  operator if cleanup of concat files is desired; it is not added automatically.

### Tests

- `test_summarizer.py`: unit-test `concat_transcriptions` (two transcription files
  → joined with separator; no files → `SummarizationError`; `postprocessed` falls
  back to original when fix text absent).
- `test_pipeline.py` / integration: `underscore_prefix: false` → output named
  `<dirname>_sum.<ext>`; `underscore_prefix: true` → output named
  `_<dirname>_sum.<ext>`; concat file always written as `.txt`; Formatter applied
  to LLM summary file only; no regression on per-file summarization.

## Acceptance Criteria

1. The per-directory combined transcription file is written before the LLM call.
2. LLM receives concatenated transcriptions (not per-file summaries).
3. With `underscore_prefix: false` (default) filenames are unchanged from today.
4. With `underscore_prefix: true` both the concat and summary files start with `_`.
5. The concat file is always `.txt`; the summary file respects `formatter.format`.
6. `concat_source: original` concatenates raw transcripts regardless of
   post-processing state.
7. `--cleanup` removes the concat and summary files when configured in
   `cleanup.targets`.
8. All existing tests pass; new tests cover the above criteria.
