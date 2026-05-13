# EPIC-013: Replace Transcription with Postprocessed Output

**Status**: Planned

## Goal

Add a `replace_transcription` config flag that, after postprocessing succeeds, moves the corrected file (`_fix.txt`) over the original transcription file (`.txt`), so downstream steps (summarization, rescan skip-check) always work from the best available text.

## Background

Currently the pipeline writes two text files side-by-side:

- `<file>.txt` — raw whisper transcription
- `<file>_fix.txt` — LLM-corrected version produced by the postprocessor

Consumers that re-read the transcript (e.g. the summarizer when `source: transcription`) always read the raw `.txt`. There is no built-in way to promote the corrected version. Users who want summarization to operate on the fixed text must either change `source` settings or post-process files manually. The `replace_transcription` flag closes this gap.

## Scope

### Config

New boolean flag under `postprocessing`:

```yaml
postprocessing:
  enabled: true
  replace_transcription: false   # default — preserves current behaviour
```

### Behaviour when `replace_transcription: true`

1. Postprocessor writes `<file>_fix.txt` as usual.
2. After a successful write, the postprocessor moves (renames) `<file>_fix.txt` → `<file>.txt`, replacing the original raw transcription.
3. No `_fix.txt` remains on disk.
4. On failure the raw `.txt` is left untouched; `<file>_err.txt` is written as normal.

### Behaviour when `replace_transcription: false` (default)

No change from current behaviour — both `.txt` and `_fix.txt` are kept.

### Rescan / skip-check compatibility

The skip-check already looks for `<file>.txt`. When `replace_transcription: true` the `.txt` is present after the first run, so the file is correctly skipped on the next run.

### Summarization source compatibility

When `replace_transcription: true`, setting `file_summarization.source: transcription` naturally reads the corrected text because `.txt` now contains it. No changes needed in the summarizer.

## Files to change

- `src/fileswhisper/config.py` — add `replace_transcription: bool = False` to the `PostprocessingConfig` dataclass
- `src/fileswhisper/pipeline/postprocessor.py` — after writing `_fix.txt`, if flag is set rename it to `.txt`
- `config/config.example.yaml` — document the new field with a comment
- `tests/test_postprocessor.py` — add cases for flag=True (file renamed) and flag=False (both files kept)

## Acceptance Criteria

- [ ] `replace_transcription` defaults to `false`; existing behaviour is unchanged when omitted or set to `false`
- [ ] When `true`, after successful postprocessing only `<file>.txt` exists (containing the fixed text); `<file>_fix.txt` does not exist
- [ ] When `true` and postprocessing fails, `<file>.txt` is unchanged and `<file>_err.txt` is written
- [ ] Rescan skip-check works correctly in both modes
- [ ] `config.example.yaml` documents the new flag
- [ ] Tests cover both flag values

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
