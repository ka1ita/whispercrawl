# EPIC-003: Summarization

**Status**: Done

## Goal

Generate per-file and per-directory summaries using ollama.

## Scope

### Per-File Summary
- `src/fileswhisper/pipeline/summarizer.py`
- Reads `<source>_fix.txt` (falls back to `<source>.txt` if fix step is disabled)
- Writes `<source>_sum.txt`
- Config section: `file_summarization` (URL, model, prompt, output suffix)

### Per-Directory Summary
- Same module, different config section: `dir_summarization`
- Collects all `_sum.txt` files in a directory, sends combined content to ollama
- Writes `<dirname>_sum.txt` in that directory
- Runs after all files in the directory have been processed

## Acceptance Criteria

- [x] Per-file `_sum.txt` is created for each processed audio file
- [x] Per-directory `<dirname>_sum.txt` aggregates all file summaries in that directory
- [x] Each summary step can be independently disabled in config
- [x] Skip logic applies per output file existence

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
