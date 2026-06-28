# EPIC-026: Formatter Speaker Style for HTML and MD

## Goal

When the output format is `html` or `md`, render speaker labels (e.g. `[SPEAKER_00]:`) with emphasis (bold or italic) and the transcript text as regular text — either on the same line or on a new line — instead of outputting raw plain text. The style is driven by two new config knobs so operators can choose without touching code.

## Background

EPIC-015 introduced diarized output formatted as `[SPEAKER_XX]: text\n` per segment. EPIC-023–025 added `html`/`md` conversion. Currently both formats copy the raw text unchanged (html wraps it in `<pre>`, md is a plain copy), so speaker labels have no visual distinction from the transcript text.

## Scope

- `config.py`: extend `FormatterConfig` with two optional fields:
  - `speaker_style: str = "bold"` — `"bold"` | `"italic"` | `"plain"` — controls emphasis applied to the speaker label.
  - `text_placement: str = "same_line"` — `"same_line"` | `"new_line"` — controls whether transcript text follows the speaker on the same line or starts on the next line.
  - Validate both in `load_config`; raise `ValueError` on unknown values.

- `pipeline/formatter.py`:
  - Add a private `_render_diarized(text: str) -> str` method that parses lines matching `[SPEAKER_XX]: ...` and reformats them according to `speaker_style` and `text_placement`.
  - Lines that do not match the speaker-label pattern are passed through unchanged.
  - **MD rendering**:
    - `bold` → `**[SPEAKER_XX]:**`
    - `italic` → `*[SPEAKER_XX]:*`
    - `plain` → `[SPEAKER_XX]:`
    - `same_line` → label + space + text on one line
    - `new_line` → label on its own line, text indented on next line
  - **HTML rendering**: replace the `<pre>` block with structured `<p>` tags; apply `<strong>` or `<em>` to the speaker label, text as plain inline content; `new_line` inserts a `<br>` between label and text.
  - Non-diarized files (no lines matching the pattern) render identically to current output.

- `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: add commented-out `speaker_style` and `text_placement` under `formatter:`.

- Tests (`tests/test_formatter.py`): add cases —
  - MD bold same_line, italic new_line, plain same_line
  - HTML bold same_line, em new_line
  - File with no speaker labels → output unchanged
  - `txt` format → style fields ignored

## Out of Scope

- CSS stylesheets or external templates for HTML.
- Changing any pipeline step other than `Formatter`.
- Per-speaker color or custom label text.

## Acceptance Criteria

1. `formatter: { format: md, speaker_style: bold, text_placement: same_line }` in config is accepted without `ValueError`.
2. A diarized `.txt` file converted to `.md` has each speaker label rendered in the chosen emphasis and text on the chosen line placement.
3. A diarized `.txt` file converted to `.html` has `<strong>`/`<em>` on speaker labels; body no longer uses `<pre>`.
4. A non-diarized file (no `[SPEAKER_XX]:` lines) is converted without modification to its content.
5. `formatter.format: txt` is unaffected by the new config fields.
6. All existing tests pass; new style tests are green.
