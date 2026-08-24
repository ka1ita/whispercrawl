# EPIC-036: Absolute Speaker Timestamps from Filename

## Goal

Add an optional postprocessing config parameter that offsets the relative `HH:MM:SS`
speaker timestamps (produced by EPIC-035) by the recording start time embedded in the
filename, turning them into wall-clock timestamps.

**Before** (relative, from transcriber):

```
[SPEAKER_04 00:00:52] something was said
[SPEAKER_05 00:01:53] another thing
```

**After** (absolute, filename `2026-08-21_09_04_40.ogg` → start `09:04:40`):

```
[SPEAKER_04 09:05:32] something was said
[SPEAKER_05 09:06:33] another thing
```

## Scope

### Config

Add `filename_timestamp_format: str | null = null` to `PostprocessingConfig`.

```yaml
postprocessing:
  # Parse recording start time from filename and add it to speaker segment
  # timestamps. Uses Python strptime directives applied to the filename stem
  # (without extension). Set to null (default) to disable.
  # Example: "%Y-%m-%d_%H_%M_%S" matches "2026-08-21_09_04_40"
  filename_timestamp_format: null
```

- When `null` (default), the step is a no-op.
- The format string uses standard Python `strptime` directives applied to
  the **filename stem** (i.e. `Path(file).stem`, no directory, no extension).
- If parsing fails (format mismatch, no match), log a WARNING and leave the
  transcript unchanged.
- Only meaningful when `speaker_timestamps: true` in the transcription config
  (timestamps must already be present in the `_fix.txt` input). If no timestamp
  pattern is found in the text, the step silently does nothing.

### PostProcessor

Add a new method `_offset_timestamps(text: str, offset: timedelta) -> str` (or
inline it into the postprocessing chain) that:

1. Finds all occurrences of `[SPEAKER_\w+ HH:MM:SS]` via regex.
2. Parses the `HH:MM:SS` value, adds `offset` (a `timedelta`), formats back as
   `HH:MM:SS`.
3. Handles wrap-around (e.g. offset pushes past midnight — format modulo 24 h).

The postprocessor already receives the source file path; use `Path(source).stem`
to extract the filename stem for `datetime.strptime(stem, format)`.

Extraction of the `timedelta` offset:

```python
dt = datetime.strptime(stem, filename_timestamp_format)
offset = timedelta(hours=dt.hour, minutes=dt.minute, seconds=dt.second)
```

(Date component is intentionally discarded — only the time-of-day portion is used.)

Apply `_offset_timestamps` **after** the existing regex cleanup and LLM correction
passes so that the timestamps being rewritten are already final.

### Config files

Add commented `filename_timestamp_format: null` line under `postprocessing:` in:
- `config.yaml`
- `deploy/prod/config.yaml`
- `deploy/prod-local/config.yaml`

## Acceptance Criteria

- `filename_timestamp_format: null` (default) — postprocessing output is unchanged.
- Valid format + matching filename → each `[SPEAKER_XX HH:MM:SS]` in the output is
  shifted by the recording start time.
- Timestamp arithmetic wraps correctly (e.g. offset `23:59:00` + `00:01:30` →
  `00:00:30`).
- Format mismatch or unparseable filename → WARNING logged, text returned unchanged,
  no exception propagated.
- No speaker timestamps present in text → step is a no-op (no error).
- `filename_timestamp_format` set but `speaker_timestamps: false` → nothing to
  rewrite; step silently does nothing.

## Out of Scope

- Using the date component of the parsed filename timestamp.
- Reformatting the timestamp display (HH:MM:SS stays HH:MM:SS).
- Applying the offset to non-diarized plain-text transcripts.
- Auto-detecting the filename format.
