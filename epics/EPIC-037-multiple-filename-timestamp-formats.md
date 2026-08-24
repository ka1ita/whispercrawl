# EPIC-037: Multiple `filename_timestamp_format` Values

## Goal

`filename_timestamp_format` (added in [[EPIC-036-absolute-speaker-timestamps]]) currently
accepts a single `strptime` format string. Recordings arrive with inconsistent filename
conventions (e.g. `2026-08-21_09_04_40.ogg` vs `2026-08-21-09-04-40.ogg`), so a single
format is not enough to cover a watch_dir with mixed naming. Allow `filename_timestamp_format`
to be a list of format strings, tried in order, so the first one that parses the filename
stem is used.

## Scope

### Config

Widen `filename_timestamp_format` on `PostprocessingConfig` to accept either a single
string (existing behavior, kept for backward compatibility) or a list of strings.

```yaml
postprocessing:
  # Parse recording start time from filename and add it to speaker segment
  # timestamps. Uses Python strptime directives applied to the filename stem
  # (without extension). Accepts a single format string or a list of formats —
  # each is tried in order until one parses the filename stem. Set to null
  # (default) to disable.
  filename_timestamp_format:
    - "%Y-%m-%d_%H_%M_%S"
    - "%Y-%m-%d-%H-%M-%S"
```

- A bare string remains valid and behaves as a single-element list.
- `null` (default) keeps the step disabled.
- Formats are tried in the listed order; the first one that successfully parses the
  filename stem via `datetime.strptime` wins.
- If none of the formats parse the filename stem, log a single WARNING (listing the
  formats tried) and leave the transcript unchanged — same failure behavior as today.

### PostProcessor

Update the `filename_timestamp_format` handling in `PostProcessor.process` to loop over
the configured formats (normalizing a bare string into a one-item list) instead of
calling `datetime.strptime` once, stopping at the first successful parse.

### Config files

Update the commented example under `postprocessing:` in:
- `config.yaml`
- `deploy/prod/config.yaml`
- `deploy/prod-local/config.yaml`

to show the list form.

## Acceptance Criteria

- `filename_timestamp_format: null` (default) — postprocessing output is unchanged.
- `filename_timestamp_format` as a single string — behaves exactly as before (regression
  coverage for existing EPIC-036 tests).
- `filename_timestamp_format` as a list — a filename matching any one of the formats has
  its timestamps offset using that format's parsed start time.
- Filename matches none of the listed formats → one WARNING logged, text returned
  unchanged, no exception propagated.
- Order matters: if a filename stem happens to parse under more than one listed format,
  the first matching format in the list is used.

## Out of Scope

- Auto-detecting filename formats without an explicit config list.
- Per-file or per-directory format overrides.
- Changing the offset arithmetic or timestamp regex from [[EPIC-036-absolute-speaker-timestamps]].
