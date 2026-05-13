# EPIC-011: Summarization Source Selection

**Status**: Done

## Goal

Allow the user to choose whether per-file summarization reads the post-processed transcript (`_fix.txt`) or the raw transcription (`.txt`) as its input, via a single config flag.

## Background

Currently the summarizer always reads `<file>_fix.txt` (post-processed output) when building the per-file summary. Some workflows skip post-processing entirely (`llm_enabled: false`, `regex_enabled: false`) or produce better summaries from the raw text. Users need control over which file is fed to the summarizer without changing the pipeline structure.

## Scope

- Add `summarize_source` field to `file_summarization` config section (values: `"postprocessed"` | `"original"`)
- Implement source selection in `Summarizer` / `Runner`: when `"original"`, read `<stem>.txt`; when `"postprocessed"`, read `<stem>_fix.txt` (current behaviour, new default)
- If the chosen source file does not exist, fall back to the other variant and log a warning; if neither exists, skip summarization for that file
- Update `config/config.example.yaml` with the new field and inline comment
- Update unit/integration tests

## Config Interface

```yaml
file_summarization:
  summarize_source: postprocessed   # "postprocessed" (_fix.txt) | "original" (.txt)
  llm_enabled: true
  model: gemma3:1b
  prompt: |
    ...
```

## Acceptance Criteria

- [x] `summarize_source: postprocessed` (default) — behaviour identical to current: summarizer reads `_fix.txt`
- [x] `summarize_source: original` — summarizer reads `.txt` instead
- [x] If the preferred source file is missing, fall back to the other and log a `WARNING`
- [x] If neither source exists, summarization step is skipped for that file with a `WARNING`
- [x] Config example documents the field with both valid values
- [x] Existing tests pass; new tests cover both source modes and the fallback logic

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
