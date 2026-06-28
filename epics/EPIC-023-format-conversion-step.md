# EPIC-023: Centralize Output Format Conversion in a Final Formatter Step

**Status**: Open

## Goal

Move `render_output()` out of every individual pipeline step and into a single **Formatter** step that runs last, after all other steps have completed for a given run.

Each pipeline step (Transcriber, PostProcessor, Summarizer) will write plain `.txt` files internally. The Formatter reads those `.txt` files and rewrites them in the configured `output_format`, then removes the `.txt` originals when format is not `txt`.

## Background

EPIC-022 added `output_format` support by calling `render_output()` before each `write_text()` call across every step. This has two problems:

1. **LLM gets HTML as input.** `summarize_directory()` reads `*_sum.html` files and passes the full HTML markup (`<!DOCTYPE html><html>...`) to the LLM — the model sees boilerplate noise instead of clean text.
2. **Rendering is scattered.** Every step has to know about `output_format`, making format logic a cross-cutting concern rather than a single responsibility.

Centralizing the conversion removes both problems: the pipeline always produces `.txt` internally; a single Formatter step applies the format change to all result files at the very end.

---

## Scope

### Pipeline steps → always write `.txt`

Remove the `render_output()` call from every `write_text()` in `run_pipeline()` in `main.py`. Steps always write plain `.txt` regardless of `output_format`.

The `output_path()` helper is simplified: always use `.txt` extension when generating the path for pipeline steps.

### Summarizer reads `.txt`

`summarize_directory()` in `pipeline/summarizer.py` always globs `*{file_sum_suffix}.txt`. Remove the `output_format` parameter from its signature; the format is no longer relevant at read time.

### New Formatter step — `pipeline/formatter.py`

Create `class Formatter`:

```python
class Formatter:
    def __init__(self, output_format: str) -> None: ...

    def format_file(self, txt_path: Path) -> Path:
        """Read txt_path, write converted file, remove txt_path. Return new path."""
        ...

    def format_all(self, base: Path, suffixes: list[str]) -> None:
        """Format all output files for a given base (media file or dir base)."""
        ...
```

- For `output_format == "txt"`: `format_file` is a no-op (returns `txt_path` unchanged, nothing deleted).
- For `output_format == "html"`: reads `.txt`, wraps with `render_output()`, writes `.html`, deletes `.txt`.
- Error files (`_err.txt`) are also converted by the Formatter.

### Integration in `run_pipeline()`

After all file-level steps complete (including `cleaner.clean()`), the Formatter converts all output files written for that media file. After the directory summarizer step completes, the Formatter converts the directory summary file.

Order per media file:
1. Transcribe → `<stem>.txt`
2. PostProcess → `<stem>_fix.txt` (may replace `<stem>.txt` via `replace_transcription`)
3. File summarize → `<stem>_sum.txt`
4. **Formatter** → convert all of the above to final format

Order per directory (after all files in that dir):
5. Dir summarize → `<dirname>_sum.txt`
6. **Formatter** → convert dir summary to final format

### `output_path()` helper

`output_path()` in `main.py` continues to exist but is only called by the Formatter and by `run_cleanup()`. Pipeline steps derive their internal `.txt` paths without it (or via a new `txt_path()` helper that always uses `.txt`).

### `run_cleanup()` unchanged in behavior

`run_cleanup()` already uses `output_path()` with the configured format — no change needed there.

### `file_walker.py` — skip check

`iter_media_files` currently derives the skip-check extension from `output_format`. After this epic, the skip-check extension is always `.txt` (pipeline writes `.txt` first), so the `output_format` parameter can be removed from `iter_media_files`.

---

## Acceptance Criteria

- [ ] `pipeline/formatter.py` exists with `Formatter` class; `format_file` is a no-op for `"txt"` and converts + replaces for `"html"`
- [ ] No `render_output()` call remains inside Transcriber, PostProcessor, or Summarizer write paths
- [ ] `summarize_directory()` always reads `.txt` files; `output_format` parameter removed from its signature
- [ ] `iter_media_files` no longer receives or uses `output_format`
- [ ] For `output_format: html`, all output files on disk after a run have `.html` extension and no orphan `.txt` files remain
- [ ] For `output_format: txt`, behaviour is identical to the pre-epic state (Formatter is a no-op)
- [ ] `run_cleanup()` still removes the correct files for both formats
- [ ] `replace_transcription: true` still works: `_fix.txt` replaces the transcript `.txt`; Formatter then converts the merged file
- [ ] Tests: html run → no `.txt` output files remain; txt run → `.txt` files present, no `.html`; dir summarizer receives plain text regardless of format; formatter no-op on txt

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
