# EPIC-045: Formatter `speaker_style` Ignored When Speaker Timestamps Are On

## Goal

`formatter.speaker_style` (`bold` / `italic` / `plain`) and `text_placement`
must style the speaker label whether or not
`transcription.speaker_timestamps` is enabled.

Today, with `speaker_timestamps: true` (the current [config.yaml](../config.yaml)
default), the `html` formatter emits an unstyled `<pre>` dump and the `md`
formatter passes every line through untouched — `speaker_style` has no effect.

## Problem Description

The transcriber emits two different speaker-line shapes
([`transcriber.py:148-157`](../src/whispercrawl/pipeline/transcriber.py#L148-L157)):

| `speaker_timestamps` | line format |
| --- | --- |
| `false` | `[SPEAKER_00]: text` |
| `true` (+ start time) | `[SPEAKER_00 00:00:01] text` |
| `true` (no start time) | `[SPEAKER_00] text` |

The formatter only recognises the first
([`formatter.py:8`](../src/whispercrawl/pipeline/formatter.py#L8)):

```python
_SPEAKER_RE = re.compile(r'^\[([^\]]+)\]:\s*(.*)')
```

The `\]:` requires a colon immediately after the closing bracket. The
timestamp forms have a space there, not a colon, so:

- `_render_html` sees `has_speakers == False` → whole file wrapped in `<pre>`,
  no `<strong>` / `<em>`, no `<p>` wrapping.
- `_render_md` matches no lines → every line passed through verbatim, no
  `**` / `*` emphasis, no `text_placement` handling.

Observed in `audio/Levitan_02.02.1943 copy.html`: a `<pre>` block of
`[SPEAKER_00 00:00:01] …` lines despite `speaker_style: bold`.

This has been latent since EPIC-035 introduced the timestamped label; EPIC-026
(`speaker_style`) predates it and was only ever tested against the colon form.

## Scope

### `src/whispercrawl/pipeline/formatter.py`

- Broaden `_SPEAKER_RE` to match all three shapes, anchored to a `SPEAKER_`
  label so ordinary bracketed text is not captured. The colon and the
  bracket-internal timestamp are both optional; capture the colon so it can be
  reproduced (not injected):

  ```python
  _SPEAKER_RE = re.compile(r'^\[(SPEAKER_[^\]]*?)\](:?)\s*(.*)$')
  ```

  - `[SPEAKER_00]: text`      → label `SPEAKER_00`, colon `:`, text `text`
  - `[SPEAKER_00 00:00:01] t` → label `SPEAKER_00 00:00:01`, colon ``, text `t`
  - `[SPEAKER_00] text`       → label `SPEAKER_00`, colon ``, text `text`

- `_md_speaker_line(label, colon, text)` and
  `_html_speaker_line(label, colon, text)`: build the styled token as
  `[{label}]{colon}` — i.e. keep the trailing colon only when the source line
  had one. Existing colon-form output is unchanged
  (`**[SPEAKER_00]:**`); the timestamp form renders `**[SPEAKER_00 00:00:01]**`.

- Update the three call sites (`_render_md`, `_render_html` speaker branch, and
  the `has_speakers` check) for the new group indices.

### Non-changes

- No new config. Both label shapes are existing, valid whispercrawl output.
- `txt` format still a no-op.
- Lines that don't start with `[SPEAKER_…]` still pass through untouched
  (`md`) / become `<p>…</p>` or are dropped when blank (`html`), as today.
- Already-generated `.html` / `.md` files are not retro-fixed — re-run with
  `rescan: true` (or clear the affected index rows / delete the outputs) to
  regenerate.

## Files to change

- `src/whispercrawl/pipeline/formatter.py` — `_SPEAKER_RE`, `_md_speaker_line`,
  `_html_speaker_line`, call sites.
- `tests/test_formatter.py` — new cases (below).
- `docs/architecture/overview.md` — note that `speaker_style` covers the
  timestamped label form.

## Acceptance Criteria

- [x] `[SPEAKER_00 00:00:01] Hello` with `format: html`, `speaker_style: bold`
  renders `<p><strong>[SPEAKER_00 00:00:01]</strong> Hello</p>` — no `<pre>`.
- [x] Same line with `speaker_style: italic` → `<em>[SPEAKER_00 00:00:01]</em>`.
- [x] Same line with `speaker_style: plain` → `[SPEAKER_00 00:00:01] Hello`
  inside a `<p>`, no `<strong>`/`<em>`.
- [x] Same line with `text_placement: new_line` (html) inserts `<br>` between
  label and text; (md) inserts `\n`.
- [x] `[SPEAKER_00 00:00:01] Hello` with `format: md`, `speaker_style: bold`
  renders `**[SPEAKER_00 00:00:01]** Hello` (no injected colon).
- [x] `[SPEAKER_00] Hello` (timestamps on, no start time) is styled the same way,
  label `[SPEAKER_00]` with no colon.
- [x] Existing colon-form assertions still pass verbatim
  (`**[SPEAKER_00]:** Hello world`, `<strong>[SPEAKER_00]:</strong> Hello world`).
- [x] A non-speaker line beginning with `[` (e.g. `[music]`) is **not** treated
  as a speaker line.
- [x] Trailing-newline preservation and the txt no-op cases still pass.

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
