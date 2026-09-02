# ADR-004: Multiple ASR Engines With Per-Engine Results

**Date**: 2026-09-01
**Status**: Accepted

## Context

`transcription` was a single `TranscriptionConfig` with one `url`. Comparing a
second `whisper-asr-webservice` deployment, engine, or parameter set against the
current one meant editing config, a full `rescan: true`, saving the outputs
elsewhere, reverting, and running again — and the EPIC-046 index stored one
`asr_text` / `fixed_text` per file, so a second engine would overwrite the first.

## Decision

`transcription` gains an optional `engines:` list. Each entry is merged onto the
top-level `transcription` block (entry values win, unset fields inherit) and has
a filename-safe, unique `name`. `load_config` resolves this into
`config.transcription.engines` — a non-empty list of `TranscriptionConfig`. With
no `engines:` key `Config.__post_init__` fills the list with a copy of the base
block, `name == ""` — so iterating `config.transcription.engines` is the single
way to reach the engine set, single- and multi-engine alike.

- **`engine_label(name)`** → `"_<name>"` for a named engine, `""` for the
  implicit one. Applied to every result / error filename and every
  processing-index key. The `name == ""` path is byte-identical to pre-048.
- **Pipeline**: `_transcribe_file` runs every engine and returns one context per
  engine that produced a transcript; `_postprocess_one` / `_summarize_one` /
  `_finalize_one` take a single per-engine context and thread the engine through
  every `output_path` and state call. `processing_mode` still applies —
  `per_step` batches each step across all `(file, engine)` pairs. `_finalize_file`
  records the file `done` only once every engine finished, `error` otherwise
  (detail names the failed engines).
- **Index** (`state.py`, schema v4): a single `asr_results(path, engine, kind,
  text, mtime, size)` table holds every engine's text, `engine == ""` included.
  The EPIC-046 `files.asr_text` / `fixed_text` columns are dropped — the feature
  had not shipped, so no data migration was needed and one code path is simpler
  than a branch on `engine`. Step tokens for a named engine are suffixed
  `:<name>`; `mark_step`'s mtime/size-mismatch reset deletes the file's
  `asr_results` rows.
- **Isolation**: one engine's `TranscriptionError` writes
  `<file>_<name>_err.txt` and drops only that engine; the others still produce
  results, and the next run resumes the succeeded engines from the index and
  retries only the failed one.
- **`--refresh`**: loops engines; regenerates each from its stored text; an
  engine with no stored text for a file is skipped (INFO, no `_err.txt`).
- **Cleanup**: `run_cleanup` and `Cleaner` iterate the configured engine labels,
  removing `<stem><label><suffix>.<ext>` and per-engine dir results.

## Alternatives considered

- **Keeping the `files.asr_text` / `fixed_text` columns for `engine == ""` and
  a side table only for named engines.** Was the first cut (zero-migration), but
  once it was clear EPIC-046's text store had not been deployed, collapsing to
  one table removed a real branch from `save_text` / `get_text` / `mark_step` at
  no cost.
- **A separate config file per engine.** Rejected — the engine set is a property
  of one install; running N configs loses the shared traversal state and the
  single index.
- **Concurrent transcription across engines.** Deferred — engines run
  sequentially; a parallel executor is a later optimization and orthogonal to
  the storage/naming model.
- **A merged / "best-of" transcript across engines.** Out of scope — each
  engine's output stays separate; diffing or picking is a downstream tool.

## Consequences

- A folder processed with two engines holds two results per recording and two
  per directory, each independently regenerable with `--refresh`.
- `max_files_per_run` counts files, not `file × engine` — a capped run may do
  more service calls than the cap suggests.
- Downstream steps (`postprocessing`, `*_summarization`) use the single existing
  config for every engine; per-engine downstream overrides can be added later if
  needed.
- Removing an engine from `engines:` and re-running does not reprocess the
  engines already `done` (their `step:<name>` tokens and text remain); their old
  result files are swept by the next `--cleanup`.
- Changing `speaker_timestamps` / `diarize` / `language` for an engine still
  needs a real re-transcribe (`rescan: true`), same as the single-engine case.
- Schema v4 drops `files.asr_text` / `fixed_text`. A dev DB created at v3 keeps
  those (now-unread) columns — harmless; `state.db` is safe to delete and
  rebuilds from existing output files.
