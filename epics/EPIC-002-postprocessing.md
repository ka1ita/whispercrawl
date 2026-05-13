# EPIC-002: Post-Processing

**Status**: Done

## Goal

Clean transcription output using two passes:
1. Regex-based cleanup (remove known artifacts)
2. LLM-based correction via ollama prompt

## Scope

- `src/fileswhisper/pipeline/postprocessor.py`
- Reads `<source>.txt`, writes `<source>_fix.txt`
- Config section: `postprocessing` (ollama URL, model, prompt, regex patterns, output suffix)

## Acceptance Criteria

- [x] Regex patterns from config are applied before LLM call
- [x] LLM prompt wraps the transcription text and returns corrected text
- [x] `_fix.txt` is only written on success
- [x] If `_fix.txt` already exists and mode is `skip-processed`, step is skipped
- [x] On ollama error, `_err.txt` is written for this step

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
