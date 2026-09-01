# ADR-002: Strip the Speaker Prefix Embedded in Whisper Segment Text

**Date**: 2026-09-01
**Status**: Accepted

## Context

When EPIC-015 added JSON diarization, `whisper-asr-webservice` returned segments
with clean `text` and a separate `speaker` key, e.g.
`{"speaker": "SPEAKER_00", "text": "hello"}`. `Transcriber._format_diarized`
builds whispercrawl's own label (`[SPEAKER_00]: ` or, with `speaker_timestamps`,
`[SPEAKER_00 HH:MM:SS] `) from the `speaker` key and prepends it to `text`.

A later `whisper-asr-webservice` version (whisperx engine) also prepends
`[SPEAKER_xx]: ` to the `text` field itself. The `speaker` key is still present.
The result is a doubled label on every line:

```
[SPEAKER_00 00:04:23] [SPEAKER_00]: евгений здравствуй ...
```

The postprocessor's timestamp-offset regex only rewrites the first bracket, so
the duplicate also reaches `_fix` output and every downstream summary.

## Decision

In `_format_diarized`, strip a leading `[SPEAKER_xx]:` / `[SPEAKER_xx]` tag from
every segment's `text` (module-level `_EMBEDDED_SPEAKER_RE` +
`_strip_embedded_speaker`, applied in both the speaker-present and no-speaker
branches). The label whispercrawl emits still comes solely from the `speaker`
key; the embedded tag is only ever removed, never used as a fallback.

No config flag — the embedded tag is never desired output. The `diarize_log`
sidecar keeps storing the raw response body verbatim.

## Consequences

- Diarized transcripts carry exactly one speaker label per line again, in
  whispercrawl's configured format, regardless of the service version.
- whispercrawl is now resilient to this service-side formatting change; if a
  future version stops embedding the tag, the strip is a harmless no-op.
- Transcripts already written with the doubled label are not retro-fixed —
  re-run with `rescan: true` (or delete the `.txt` / clear the index rows) to
  regenerate them.
- A pathological segment whose real content happens to start with a literal
  `[SPEAKER_00]:` string would lose that prefix. Considered acceptable — such
  text does not occur in speech transcripts.
