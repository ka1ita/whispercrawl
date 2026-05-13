# EPIC-014: Diarization Response Logging

**Status**: Planned

## Goal

When `diarize: true`, save the raw whisper API response in JSON format alongside
the plain-text transcript so diarization results can be inspected and debugged.

## Background

The transcriber currently calls `/asr?output=txt&diarize=true`. The `txt` output
format flattens speaker labels — if diarization silently fails (missing model,
unsupported engine, HuggingFace token not set, etc.) the plain-text output is
indistinguishable from a non-diarized result. There is no artifact to inspect.

The whisper-asr-webservice also accepts `output=json`, which returns a structured
response including per-segment speaker labels, start/end timestamps, and
confidence scores. Saving this response as a sidecar file makes it possible to:

- Confirm diarization ran and produced speaker segments.
- See how many speakers were detected and when they speak.
- Compare across runs (e.g. after changing engine or model).

## Scope

### New config flag

```yaml
transcription:
  diarize: true
  diarize_log: true   # save raw JSON response to <file>_diarize.json (default: false)
```

`diarize_log` is only meaningful when `diarize: true`. When `diarize: false` or
`diarize_log: false`, no extra request is made.

### Behaviour when `diarize_log: true`

1. After the normal `output=txt` request succeeds, make a second POST to `/asr`
   with identical params except `output=json`.
2. Write the raw JSON response body to `<file>_diarize.json` beside the audio file.
3. Errors in the second request are logged as warnings and do not fail the pipeline
   (the `.txt` transcript is already written — the JSON log is best-effort).
4. The `_diarize.json` file is included in cleanup targets when `--cleanup` runs.

### What to look for in the JSON

The whisperx engine returns something like:

```json
{
  "segments": [
    {
      "start": 0.0, "end": 3.5, "text": "Hello everyone.",
      "speaker": "SPEAKER_00"
    },
    ...
  ]
}
```

If diarization failed or the engine doesn't support it, `speaker` keys will be
absent from all segments. That is the diagnostic signal.

### Rescan / skip-check

The skip-check looks for `<file>.txt`. The `_diarize.json` sidecar does not
affect skip logic.

## Files to change

- `src/fileswhisper/config.py` — add `diarize_log: bool = False` to
  `TranscriptionConfig`
- `src/fileswhisper/pipeline/transcriber.py` — after successful txt transcription,
  if `diarize_log` is set make second JSON request and write `_diarize.json`
- `config/config.yaml` — document the new flag with a comment
- `tests/test_transcriber.py` — add cases: flag off (no second call), flag on
  (second call made, file written), flag on + second request fails (warning logged,
  no crash)

## Acceptance Criteria

- [ ] `diarize_log` defaults to `false`; no extra HTTP call is made when omitted
- [ ] When `diarize: true` and `diarize_log: true`, `<file>_diarize.json` is
  written with the raw JSON response from whisper
- [ ] A failure in the JSON request logs a warning but does not raise an exception
  or write `_err.txt`
- [ ] When `diarize: false`, `diarize_log` is ignored (no second request)
- [ ] `--cleanup` removes `_diarize.json` files
- [ ] `config/config.yaml` documents the flag
- [ ] Tests cover: flag off, flag on success, flag on second-request failure

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
