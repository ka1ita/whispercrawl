# EPIC-060: Time-Only `filename_timestamp_format`

## Goal

New recordings arrive with **time-only** filenames (`09_04_40.ogg`,
`09-04-40.ogg`) — the date is no longer part of the name. Switch the configured
`filename_timestamp_format` list ([[EPIC-037-multiple-filename-timestamp-formats]])
from full datetime formats to time-only formats, while files already on disk with
the legacy date-prefixed names (`2026-08-21_09_04_40.ogg`,
`2026-08-21-09-04-40.ogg`) must **keep** getting their speaker timestamps offset
([[EPIC-036-absolute-speaker-timestamps]]) — a watch dir can hold both naming
generations at once.

```yaml
# before
filename_timestamp_format:
  - "%Y-%m-%d_%H_%M_%S"
  - "%Y-%m-%d-%H-%M-%S"

# after
filename_timestamp_format:
  - "%H_%M_%S"
  - "%H-%M-%S"
```

## Problem Description

- `datetime.strptime(stem, fmt)` requires the **whole** stem to match. With the
  new time-only formats configured, a stem like `2026-08-21_09_04_40` fails with
  "unconverted data remains" — every legacy file would log
  `Cannot parse timestamp from filename …` and silently lose its wall-clock
  offset on the next re-transcription.
- Old files are re-processed whenever their result is rebuilt (mtime/size change,
  `--refresh`, index reset), so this is not a one-time migration concern: both
  naming generations coexist indefinitely.
- Adding all four formats to the config would work, but the config should
  describe the **current** naming convention; legacy support belongs in the
  parser, not in every operator's config.

## Scope

### Config files

Replace the two full-datetime entries with the time-only pair in:

- `config.yaml`
- `deploy/dev/config.yaml`
- `deploy/prod/config.yaml`
- `deploy/prod-local/config.yaml`

(also dropping `deploy/prod-local`'s accidental third duplicate entry) and
update the inline example comments (`"%H_%M_%S"` matches `09_04_40`).

### PostProcessor

Extract the parse loop in `PostProcessor.process`
([postprocessor.py](../src/asr_crawler/pipeline/postprocessor.py)) into a
`_parse_stem_time(stem, formats)` helper with two passes:

1. **Full stem** — each format tried in order (unchanged [[EPIC-037]] behavior;
   new time-only names match here, and any config still listing the old
   full-datetime formats keeps working).
2. **Trailing-segment fallback** — if nothing matched, retry each format against
   every suffix of the stem that starts after a non-alphanumeric separator
   (longest suffix first, formats in config order). For
   `2026-08-21_09_04_40` the suffix `09_04_40` parses with `%H_%M_%S`; for
   `2026-08-21-09-04-40` the suffix `09-04-40` parses with `%H-%M-%S`.

The date component was always discarded (only `dt.hour/minute/second` feed the
offset), so parsing just the trailing time segment yields the identical offset
the old formats produced. Failure behavior is unchanged: no match in either
pass → one WARNING, transcript returned as-is.

## Acceptance Criteria

- Filename `09_04_40.ogg` with the new config → timestamps offset by 09:04:40
  (first format, full-stem match).
- Filename `09-04-40.ogg` with the new config → offset via `%H-%M-%S` (second
  format).
- Legacy filename `2026-08-21_09_04_40.ogg` with the new config → same offset as
  the old full-datetime config produced (`09:04:40`), via the trailing-segment
  fallback; no WARNING.
- Legacy dashed filename `2026-08-21-09-04-40.ogg` with the new config →
  offset via the `%H-%M-%S` suffix.
- Config still listing a full-datetime format (str or list) → unchanged
  behavior (full-stem pass).
- Unparseable stem (`unexpected_name.ogg`) → one WARNING, text unchanged.
- `filename_timestamp_format: null` / no `source_path` → no-op, as today.

## Tests

- `tests/test_absolute_speaker_timestamps.py`: existing cases keep their
  old-style filenames but are driven by the new time-only format list (they now
  exercise the fallback); new cases cover `09_04_40.ogg` / `09-04-40.ogg`
  full-stem matches with both single-format and list configs.

## Out of Scope

- Auto-detecting filename formats without config (unchanged from [[EPIC-037]]).
- Using the date component of legacy filenames for anything.
- Renaming existing legacy files on disk.
- Changing the offset arithmetic or the timestamp regex from
  [[EPIC-036-absolute-speaker-timestamps]].
