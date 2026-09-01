# ADR-003: One Consolidated Result File Per Audio File and Per Directory

**Date**: 2026-09-01
**Status**: Accepted

## Context

Before EPIC-047 a single recording could leave up to five files beside it —
`<file>.<ext>` (transcript), `<file>_fix.<ext>`, `<file>_sum.<ext>`,
`<file>_diarize.json`, `<file>_err.txt` — and a directory left two
(`_<dirname>_all.<ext>` concat + `_<dirname>_sum.<ext>` summary). For a folder of
40 recordings that is 80–200 files, and the people who work in the audio
directory could not tell the deliverable from the scratch work.

`postprocessing.replace_transcription: true` was itself a workaround to cut one
file, at the cost of destroying the raw transcript. EPIC-046 removed that cost by
storing the raw ASR transcript and the post-processed text in the processing
index (`state.db`), keyed to each file's `mtime`/`size`.

## Decision

Assemble one plain-text result document per file and per directory from ordered
sections (`pipeline/composer.py`), then hand it to the existing `Formatter`.

- **Per file** → `<file>.<ext>`: `result.file_sections` — the per-file summary
  (when `file_summarization` is enabled) then the transcript body. The body is
  the post-processed text when post-processing ran, else the raw transcript.
- **Per directory** → `_<dirname>.<ext>` (or `<dirname>.<ext>` when
  `dir_summarization.underscore_prefix: false`): `result.dir_sections` — the
  directory summary then every transcript concatenated with filename headers.
- Sections are emitted as markdown `#` headings (level from
  `result.heading_level`), separated by `result.separator`. A single surviving
  section is emitted bare — no heading — unless
  `result.include_missing_headings` is set. The `Formatter` renders those
  headings and `---` rules: `md`/`txt` pass through, `html` → `<h1>…`/`<hr>`.
- `postprocessing.replace_transcription`, `file_summarization.output_suffix`,
  `dir_summarization.concat_suffix` / `output_suffix` become **deprecated
  no-ops**: parsed without error, config load logs a WARNING.
- The raw ASR and intermediate post-processed text are **only** in the index.
  Resume and `--refresh` read the transcript back from there; a step failure
  leaves only `_err.txt` (the transcript is safe in the index).
- `--cleanup` and the default `cleanup.targets` gain the legacy labels
  (`_fix` / `_sum` / `_all` / `_concat`) so one pass sweeps an upgraded catalog.

## Alternatives considered

- **Keep the sidecars, add an index for discovery.** Rejected — does not solve
  the "which file is the deliverable" problem in a plain file manager or a
  synced share.
- **Multiple config files, one per output shape.** Rejected — the shape is a
  property of one install, not something to switch per run.
- **Wide `summary` column vs. keeping the summary out of the index.** The
  per-file summary is recomputed on resume rather than stored — it is one cheap
  Ollama call relative to ASR, and not storing it keeps the index schema
  focused on the expensive artifact.

## Consequences

- A processed folder contains exactly one file per recording plus one per
  directory; `_err.txt` appears only when a file needs attention.
- Iterating on the fix prompt, the summary model, the `formatter`, or the new
  `result:` section is a `--refresh` away — no whisper calls.
- A step failure now yields **no** partial file beside the audio (previously the
  raw `.txt` survived). The transcript is still recoverable from the index.
- Upgrading a pre-047 catalog: run `whispercrawl --cleanup` once, then
  `--refresh` (or `rescan: true`) to regenerate results in the single-file form.
- `replace_transcription` in an existing config keeps working (as a no-op) and
  logs a WARNING; no config is broken by the upgrade.
