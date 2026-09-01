# EPIC-044: Strip the Speaker Prefix the Whisper Service Embeds in Segment Text

## Goal

Stop the doubled speaker label in diarized transcripts:

```
[SPEAKER_00 00:04:23] [SPEAKER_00]: евгений здравствуй что за поставка...
```

Each line should carry the label exactly once, in whispercrawl's own format:

```
[SPEAKER_00 00:04:23] евгений здравствуй что за поставка...
```

## Problem Description

Current `whisper-asr-webservice` (whisperx engine, `diarize=true`, `output=json`)
returns each segment with the speaker tag **already prepended to the `text`
field**, in addition to the separate `speaker` key:

```json
{"start": 263.93, "end": 278.46,
 "text": "[SPEAKER_00]: евгений здравствуй что за поставка...",
 "speaker": "SPEAKER_00"}
```

(Confirmed from `logs/service_requests.ndjson` for
`audio/_private/cabinet2/2025-12-20_10-40-24.ogg`.)

[`Transcriber._format_diarized`](../src/whispercrawl/pipeline/transcriber.py#L98)
reads the `speaker` key and prepends its own label
(`[SPEAKER_00 00:04:23] ` or `[SPEAKER_00]: `) to the raw `text` — which still
begins with `[SPEAKER_00]: `. Result: the label appears twice on every line.

When EPIC-015 introduced JSON diarization the service returned clean segment text
(see the `text: "hello"` fixtures in `tests/test_transcriber.py`); a later service
version changed this.

The postprocessor's timestamp-offset regex
([`_TIMESTAMP_RE`](../src/whispercrawl/pipeline/postprocessor.py#L17)) only shifts
the first bracket, so the second `[SPEAKER_00]:` also survives into `_fix` output.

## Scope

### `src/whispercrawl/pipeline/transcriber.py`

- Add `import re`.
- Add a module-level pattern and helper:

  ```python
  _EMBEDDED_SPEAKER_RE = re.compile(r"^\s*\[SPEAKER_[0-9A-Za-z_]+\]\s*:?\s*")

  def _strip_embedded_speaker(text: str) -> str:
      """Remove a leading '[SPEAKER_xx]:' / '[SPEAKER_xx]' tag some
      whisper-asr-webservice versions prepend to each segment's text."""
      while True:
          stripped = _EMBEDDED_SPEAKER_RE.sub("", text, count=1)
          if stripped == text:
              return text
          text = stripped
  ```

  The loop covers a doubled/tripled embedded prefix defensively; one pass is the
  normal case.

- In `_format_diarized`, apply it to every segment's text immediately after
  `text = seg.get("text", "").strip()`, then re-check for emptiness:

  ```python
  text = _strip_embedded_speaker(seg.get("text", "").strip()).strip()
  if not text:
      continue
  ```

  This runs in **both** the speaker-present branch and the no-speaker fallback
  branch (`"\n".join(...)`), so a stray embedded tag is removed regardless.

- The `speaker` value used for whispercrawl's own label still comes from the
  `speaker` key, unchanged. The embedded tag is only ever removed, never used as a
  fallback (the `speaker` key has always been present when the service embeds the
  tag).

### Non-changes

- No config flag — the embedded tag is never desired output.
- `diarize_log` sidecar still stores the **raw** JSON body verbatim (unchanged) —
  it is a diagnostic record of what the service returned.
- No postprocessor change — once the transcriber output is clean, the single
  remaining `[SPEAKER_xx HH:MM:SS]` bracket is handled by the existing regex.
- Already-processed transcripts are not retro-fixed; re-run with `rescan: true`
  (or delete the affected `.txt` / clear the index rows) to regenerate them.
  Out of scope for this epic.

## Files to change

- `src/whispercrawl/pipeline/transcriber.py` — `re` import, `_EMBEDDED_SPEAKER_RE`,
  `_strip_embedded_speaker`, call site in `_format_diarized`.
- `tests/test_transcriber.py` — new cases (below).
- `docs/architecture/decisions/` — short ADR noting the service now embeds the tag
  and whispercrawl strips it.

## Acceptance Criteria

- [x] A segment `{"speaker": "SPEAKER_00", "text": "[SPEAKER_00]: Hello."}` with
  `speaker_timestamps=false` formats to `[SPEAKER_00]: Hello.` (one label).
- [x] The same segment with `speaker_timestamps=true` and `start=52.0` formats to
  `[SPEAKER_00 00:00:52] Hello.` (one label, no embedded tag).
- [x] A segment whose embedded tag differs from the `speaker` key
  (`{"speaker": "SPEAKER_01", "text": "[SPEAKER_00]: hi"}`) uses the `speaker`
  key for the label and strips the embedded tag: `[SPEAKER_01]: hi`.
- [x] Clean segment text (no embedded tag) is unchanged — all existing
  `tests/test_transcriber.py` assertions still pass.
- [x] `[SPEAKER_00]:` with no text after it (once stripped) is skipped like any
  other empty segment.
- [x] No-speaker fallback branch also strips a stray embedded tag.
- [x] A doubled embedded prefix (`[SPEAKER_00]: [SPEAKER_00]: hi`) is fully
  removed.
- [x] `diarize_log` sidecar content is still the raw response body.

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
