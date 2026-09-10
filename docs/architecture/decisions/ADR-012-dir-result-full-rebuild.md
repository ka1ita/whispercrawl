# ADR-012: Rebuild Directory Results From the Whole Directory via the Index

**Date**: 2026-09-10
**Status**: Accepted

## Context

Since EPIC-047 a processed directory yields one consolidated result
(`_<dirname>.<ext>` = optional summary + every transcript concatenated with
filename headers). The per-directory pass built it from `dir_file_texts` — the
map of files that produced a transcript **in the current run** — and overwrote
whatever result file was already there.

That is wrong in the pipeline's normal operating mode, the incremental
scheduled run: already-`done` files are skipped by discovery, so the pass sees
only the new arrivals. Adding `d.wav` to a directory whose `a`/`b`/`c` were
processed last week replaces a summary of four recordings with a "directory"
summary of one; `max_files_per_run`-capped batches exhibit the same bug run
after run, each rewriting the result with its own subset. `--refresh`
demonstrates the correct output (every file re-enters from stored text), but it
is a manual, whole-catalog action.

The missing piece already exists: the processing index stores each file's raw
ASR and post-processed text per engine, keyed to the file's mtime/size
(EPIC-046/048/051) — exactly what `--refresh` reads back.

## Decision

The per-directory pass rebuilds each touched directory's result from **every
current media file in the directory**, not just this run's.

- **Census**: `file_walker.directory_media_files(dir_path, extensions,
  skip_marker, max_age_days)` — the direct children of the directory surviving
  the *same* filters as discovery (shared `_candidate_stat` predicate, so the
  two walks cannot drift), sorted by name. Non-recursive: a nested subdirectory
  is its own result.
- **Merge, per engine**: files processed this run contribute their in-memory
  texts (freshest for a reprocessed file); every other census file contributes
  its stored `asr`/`fixed` text via `state.get_text`. The existing
  mtime/size-match inside `get_text` gives stale-text protection for free — a
  changed file's stored text is refused, and the file is queued for a real
  re-transcribe anyway.
- **Omissions are visible, not failures**: a census file with no stored text
  (a back-filled pre-index entry, a file an engine added later never
  transcribed) is omitted from that engine's result with one WARNING naming
  the files — never an `errors` row, because nothing failed.
- **Trigger unchanged**: only directories with in-run activity are rewritten.
  Deletion-only changes and a hand-deleted result file stay stale until a file
  in that directory is processed or `--refresh` runs.
- **No config knob.** The previous behaviour wrote a knowingly wrong result;
  that is a correctness fix, not a preference.

## Alternatives considered

- **Skip the rewrite when the run's subset is partial** (leave the old result).
  Rejected — the old result is stale the moment a file is added, and the index
  makes the *correct* result free; settling for stale-when-correct-is-cheap is
  the wrong trade.
- **Append the new files to the existing result file / parse it back.**
  Rejected — the result is a composed document (summary section + concat with
  headers); it is not round-trippable, and parsing it back would make the
  output format a data format.
- **Re-transcribe the directory or tell operators to run `--refresh`.**
  Rejected — paid whisper calls for text the index already holds; `--refresh`
  is a manual whole-catalog action for config iteration, not the answer to
  "someone dropped a new file in".
- **Census every directory eagerly during discovery.** Rejected — an extra
  walk and per-dir bookkeeping for directories nothing happened to. The census
  runs lazily, once per touched directory, per run.
- **A config knob to keep the old behaviour.** Rejected — see Decision.

## Consequences

- Incremental runs now produce the same directory result a full run or
  `--refresh` would — verified by test against a from-scratch run.
- A directory whose files predate the index (back-filled `done`, no stored
  text) gets a partial rebuild with an explicit WARNING; `rescan: true`
  remains the remedy, as before.
- One extra directory listing plus one indexed text lookup per already-done
  file per touched directory — negligible next to the ASR/LLM calls the run
  exists to make.
- `file_walker` gains a second public helper; both walks share one filter
  predicate.
- Directory results remain stale on deletion-only changes (unchanged from
  before); that stays `--refresh`'s job.
