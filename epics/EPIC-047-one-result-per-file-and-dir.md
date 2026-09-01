# EPIC-047: One Consolidated Result File Per Audio File and Per Directory

## Goal

The people who work in the audio directory want to open **one file per
recording** and **one file per folder** — not hunt through a spray of
`_fix` / `_sum` / `_all` / `_diarize.json` / `_err` sidecars.

After this epic, a processed audio file `meeting.mp3` produces exactly:

```
meeting.<ext>        # summary section, then the corrected diarized transcript
meeting_err.txt      # only on failure; absent on success
```

and a processed directory `2026-02/` produces exactly:

```
_2026-02.<ext>       # directory summary, then every transcript concatenated
_2026-02_err.txt     # only on failure
```

`<ext>` is `formatter.format` (`txt` / `md` / `html`). Everything else — the raw
ASR text, the intermediate post-processed text, the raw diarization JSON — lives
off to the side (in the processing index from [[EPIC-046]], or the log dir), not
beside the audio.

## Problem Description

The current per-file pipeline writes up to five files next to each recording:

| file | written when |
| --- | --- |
| `<file>.<ext>` | always (transcript, possibly replaced by `_fix`) |
| `<file>_fix.<ext>` | postprocessing on **and** `replace_transcription: false` |
| `<file>_sum.<ext>` | `file_summarization.llm_enabled: true` |
| `<file>_diarize.json` | `logging.diarize_log: true` |
| `<file>_err.txt` | on failure |

and per directory: `_<dirname>_all.<ext>` (concat) **plus**
`_<dirname>_sum.<ext>` (summary) — two files
([`main.py:379-404`](../src/whispercrawl/main.py#L379)).

For a folder of 40 recordings that is 80–200 files. Users scanning the folder in
a file manager or syncing it to a share can't tell the deliverable from the
scratch work, and `replace_transcription: true` was itself a workaround to cut
one file at the cost of destroying the raw transcript.

## Scope

Depends on [[EPIC-046]] (raw + fixed text in the processing index) landing
first — that removes the need to keep `_fix` / raw text on disk at all.

### 1. New composed-result step

A `result` assembly stage runs after summarization and before formatting, for
both the per-file and per-directory paths. It builds one plain-text document
from ordered sections, then hands it to the existing `Formatter`.

#### `src/whispercrawl/config.py` — `ResultConfig`

```python
@dataclass
class ResultConfig:
    file_sections: List[str] = ["summary", "transcript"]   # order; drop "summary" to omit
    dir_sections: List[str] = ["summary", "transcript"]     # "transcript" = the concat
    summary_heading: str = "Резюме"
    transcript_heading: str = "Транскрипция"
    heading_level: int = 1                                  # markdown "#" count
    separator: str = "\n\n"
    include_missing_headings: bool = False                  # skip a heading whose section produced nothing
```

Add `result: ResultConfig` to `Config`. Validate `file_sections` /
`dir_sections` entries against `{"summary", "transcript"}` in `load_config`.
A section listed but not produced (e.g. `summary` when
`file_summarization.llm_enabled: false`) is silently skipped.

#### `src/whispercrawl/pipeline/composer.py` (new)

- `compose(sections: list[tuple[str, str]], cfg: ResultConfig) -> str` — joins
  `(heading, body)` pairs as `"# {heading}\n\n{body}"` blocks separated by
  `cfg.separator`, skipping empty bodies. Emits markdown-style headings so the
  `md` formatter passes them through and the `html` formatter can render them.

#### `src/whispercrawl/pipeline/formatter.py`

- Recognise heading lines (`^#{1,6}\s+`) and horizontal rules (`^---+$`):
  - `md`: pass through unchanged (already valid).
  - `html`: `# X` → `<h1>X</h1>` (level from the `#` count), `---` → `<hr>`.
  - `txt`: pass through unchanged.
- Speaker-line styling still applies to the transcript body lines; prose lines
  in the summary section become `<p>…</p>` (html) / pass through (md) as today.
- The `has_speakers` / `<pre>` fallback in `_render_html` must not trigger just
  because a summary section has no speaker lines — always use the
  `<p>`/`<h1>` rendering path when any section is present.

### 2. `main.py` — per-file path

- Drop the `_fix` sidecar entirely (text is in the index). Drop
  `postprocessing.replace_transcription` (obsolete — the result always shows the
  best available transcript: post-processed if postprocessing ran, else raw).
  Keep the field parsing for one release as a deprecated no-op with a WARNING.
- Drop the `_sum` sidecar. The per-file summary becomes the `summary` section of
  the composed result.
- Per file: transcribe → (index) → postprocess → (index) → summarize (in
  memory) → `composer.compose([("summary", summary), ("transcript", transcript_body)], cfg.result…)`
  → write `<file>.txt` → `formatter.format_file` → `<file>.<ext>`.
- `transcript_body` = fixed text when postprocessing ran, else raw transcript.
- Per-step resume (EPIC-041): the `file_summarize` step still records
  completion; on resume the summary text comes from the index
  ([[EPIC-046]] `get_text`) — add a `"summary"` kind, or recompute (summary is
  cheap relative to ASR — recomputing on resume is acceptable; decide in impl).
- `_err.txt` beside the audio is kept — it is the one intentional signal that a
  file needs attention, and it is removed on the next success.

### 3. `main.py` — per-directory path

- Replace the two-file output (`_<dirname>_all` + `_<dirname>_sum`) with one
  composed file `_<dirname>.<ext>` (prefix per `dir_summarization.underscore_prefix`):
  `composer.compose([("summary", dir_summary), ("transcript", concat)], cfg.result, sections=cfg.dir_sections)`.
- `concat` is the existing `concat_transcriptions` output (filename headers +
  `\n\n---\n\n` between blocks).
- When `dir_summarization.llm_enabled: false`, the file is just the concat under
  its heading (still one result per directory).
- Retire `dir_summarization.concat_suffix` and `dir_summarization.output_suffix`
  (deprecated no-ops with a WARNING for one release). The dir result name is
  `{prefix}{dirname}{ext}`.

### 4. Cleanup & migration

- `pipeline/cleaner.py` / `run_cleanup`: add the now-legacy labels
  (`_fix`, `_sum`, `_all`, `_concat`) to the default `CleanupConfig.targets` and
  to `clean_other_formats`, so `--cleanup` (and a `rescan: true` run) sweep the
  old scattered files left by pre-047 runs.
- `run_cleanup` also removes `<file>_diarize.json` under the audio tree (its new
  home is the log dir, per [[EPIC-046]]).
- Docs: a short "upgrading to consolidated output" note — run
  `whispercrawl --cleanup` once, then `--refresh` (or `rescan: true`) to
  regenerate results in the new single-file form.

### 5. Config file updates

- `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`:
  - add the `result:` section with the RU headings shown above and comments;
  - remove `postprocessing.replace_transcription`,
    `file_summarization.output_suffix`, `dir_summarization.concat_suffix`,
    `dir_summarization.output_suffix` (or leave commented with a "deprecated"
    note);
  - update `cleanup.targets` to include the legacy labels for one cleanup pass;
  - update the pipeline description comments.

### 6. Docs

- `CLAUDE.md` "Processing Pipeline" + "Key Conventions": the pipeline now emits
  one composed result per file and per directory; intermediates live in the
  index / log dir; `_err.txt` is the only remaining sidecar and only on failure.
- `docs/architecture/overview.md`: redraw the per-file and per-directory output
  boxes; document the `composer` step and `ResultConfig`.
- `docs/architecture/decisions/`: an ADR for consolidating outputs and dropping
  `replace_transcription`.

## Acceptance Criteria

- [ ] A successful file run produces exactly one output beside the audio:
  `<file>.<ext>` — no `_fix`, no `_sum`, no `_diarize.json`.
- [ ] `<file>.<ext>` contains the summary section (heading + text) followed by
  the corrected diarized transcript, in `result.file_sections` order.
- [ ] With `file_summarization.llm_enabled: false`, `<file>.<ext>` is just the
  transcript (its heading omitted unless `include_missing_headings: true`).
- [ ] A successful directory run produces exactly one output:
  `_<dirname>.<ext>` (or `<dirname>.<ext>` when `underscore_prefix: false`),
  containing the directory summary then the concatenated per-file transcripts
  with filename headers.
- [ ] With `dir_summarization.llm_enabled: false`, `_<dirname>.<ext>` is the
  concat alone.
- [ ] `format: html` renders section headings as `<h1>`/`<h2>` and the
  transcript with speaker styling — no `<pre>` dump.
- [ ] `format: md` and `format: txt` produce readable composed documents.
- [ ] `_err.txt` is still written on failure and removed on the next success.
- [ ] `whispercrawl --cleanup` removes pre-047 `_fix` / `_sum` / `_all` /
  `_diarize.json` files.
- [ ] `--refresh` ([[EPIC-046]]) regenerates the composed results from stored
  text with the current `result:` / `formatter:` config and no whisper call.
- [ ] `replace_transcription` in config logs a deprecation WARNING and does not
  change behavior.
- [ ] All existing pipeline / formatter / cleaner / summarizer tests pass or are
  updated for the new output shape.

## Tests

- `tests/test_composer.py` (new): section ordering; omitted section when body
  empty; `include_missing_headings`; custom headings / separator; heading level.
- `tests/test_formatter.py`: `# Heading` → `<h1>` (html) / passthrough (md/txt);
  `---` → `<hr>` (html); a composed doc (summary prose + speaker transcript)
  renders headings + `<p>` + styled speaker lines, never `<pre>`.
- Pipeline tests: successful file run leaves only `<file>.<ext>`; content =
  summary + transcript in order; `llm_enabled: false` variants; directory run
  leaves only `_<dirname>.<ext>` with summary + concat; `--cleanup` sweeps
  legacy files; `replace_transcription: true` → WARNING, output unchanged from
  the `false` case.
- `tests/test_config.py`: `ResultConfig` defaults; invalid section name →
  `ValueError`; deprecated fields parse without error.

## Out of Scope

- **Per-file summary as a separate deliverable.** If a user wants standalone
  summaries, that is a future `result.file_sections` extra output mode, not this
  epic.
- **Embedding audio metadata / player links** in the result file.
- **Changing the diarization / speaker-label format** — the transcript body is
  exactly what the transcriber + postprocessor produce today.
- **A per-run consolidated error report.** `_err.txt` per file stays the failure
  signal; aggregating them is a separate idea.
- **Removing `_err.txt` too.** Considered and rejected — it is the one sidecar
  that earns its place (present only when action is needed).
