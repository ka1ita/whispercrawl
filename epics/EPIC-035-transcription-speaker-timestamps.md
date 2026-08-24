# EPIC-035: Speaker Timestamps in Diarized Transcription Output

## Goal

Add an optional config setting to the `transcription` step that includes each speaker's segment start time in the formatted output. When enabled, the output changes from:

```
[SPEAKER_04]: text
[SPEAKER_05]: text
```

to:

```
[SPEAKER_04 00:00:52] text
[SPEAKER_05 00:01:53] text
```

## Scope

### Config

Add `speaker_timestamps: bool = false` to `TranscriptionConfig`.

- Only meaningful when `diarize: true`. Ignored (and logged at DEBUG) when `diarize: false`.
- Format of the timestamp is `HH:MM:SS` derived from the segment `start` field (seconds, float) returned in the whisper JSON response.
- If a segment has no `start` field, the speaker label is emitted without a timestamp (graceful fallback).

### Transcriber

In `_format_diarized()`, when `speaker_timestamps: true`:

- Read `seg.get("start")` for each segment.
- Convert to `HH:MM:SS` string.
- Emit `[SPEAKER_XX HH:MM:SS] text` instead of `[SPEAKER_XX]: text`.

When `speaker_timestamps: false` (default), behaviour is unchanged.

### Config files

Add commented `speaker_timestamps: false` line under `transcription:` in:
- `config.yaml`
- `deploy/prod/config.yaml`
- `deploy/prod-local/config.yaml`

## Acceptance Criteria

- `speaker_timestamps: false` (default) — output format is unchanged (`[SPEAKER_XX]: text`).
- `speaker_timestamps: true`, segment has `start` — output is `[SPEAKER_XX HH:MM:SS] text`.
- `speaker_timestamps: true`, segment missing `start` — speaker label emitted without timestamp; no exception raised.
- `speaker_timestamps: true`, `diarize: false` — setting is silently ignored; plain-text output unchanged.
- Timestamp wraps at hours correctly (e.g. `start=3723.0` → `01:02:03`).

## Out of Scope

- Showing segment end time.
- Making the timestamp format (HH:MM:SS vs MM:SS, etc.) configurable.
- Applying timestamps to non-diarized (plain text) transcription output.
