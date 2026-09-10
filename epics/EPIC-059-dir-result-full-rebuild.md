# EPIC-059: Rebuild Directory Results From the Whole Directory

## Goal

Answer the question this epic is named for: **yes — today a newly added file
*replaces* the directory result, and the replacement is wrong.** The
per-directory pass builds `_<dirname>.<ext>` only from the files processed *in
that run* and overwrites whatever was there before. Drop `d.wav` into a
directory whose `a`/`b`/`c` were processed last week, and the next run replaces
a summary of all four recordings with a "directory" summary of `d.wav` alone.

This epic makes the per-directory pass rebuild each touched directory's result
from **every current media file in that directory**: the files processed this
run *plus* the stored `asr`/`fixed` texts the index already keeps for the
already-`done` ones ([[EPIC-046]], [[EPIC-051]]). No re-transcription, no new
config, no schema change — the corrected result is exactly what a full
`--refresh` of the same directory would produce, delivered by the ordinary
incremental run.

## Problem Description

- `dir_file_texts` ([main.py:306](../src/asr_crawler/main.py#L306)) is populated
  in `_apply_engine_result` ([main.py:441](../src/asr_crawler/main.py#L441))
  only for files that produced a transcript **this run**.
- Already-`done` files never re-enter it: `iter_media_files` skips them via
  `state.is_current` ([file_walker.py:75-79](../src/asr_crawler/file_walker.py#L75)),
  so an incremental run sees only the new arrivals.
- The per-directory pass then builds the combined document from that partial
  map and `write_text` **overwrites** the existing result
  ([main.py:703-731](../src/asr_crawler/main.py#L703)). Two symptoms of the
  same bug:
  - a new file shrinks the directory result to itself (the summary, the concat,
    everything);
  - `max_files_per_run`-capped runs each rewrite the result with *their own
    subset* — run 1 writes `a`, run 2 replaces it with `b`, and `a` is gone.
- `--refresh` already produces the correct full-directory result
  (`ignore_processed=True` → every file re-enters `dir_file_texts` from stored
  text), which confirms both the bug and the fix's shape — but nobody should
  need a refresh every time a file is added.
- The fix needs no new storage: the index keeps per-file, per-engine `asr` and
  `fixed` text keyed to the file's mtime/size
  ([state.py:48-56](../src/asr_crawler/state.py#L48),
  [state.py:206-220](../src/asr_crawler/state.py#L206)) — stale for a changed
  file, absent for a file never transcribed by that engine, current otherwise.
  `state.get_text` already encodes those semantics.

## Scope

### 1. `file_walker.py` — a direct-children census helper

- Extract the candidate predicate shared with `iter_media_files`
  (suffix ∈ `extensions`, `skip_marker`, `max_age_days`, `stat()` succeeded)
  into a private helper so the two walks cannot drift.
- New `directory_media_files(dir_path, extensions, skip_marker="",
  max_age_days=None) -> list[Path]`: **non-recursive** direct children of
  `dir_path` surviving the shared predicate, sorted by name. Non-recursive on
  purpose — a nested subdirectory is its own `dir_file_texts` key and gets its
  own result. Result files (`.txt`/`.md`/`.html`) and the `db/` directory never
  match media extensions, so no extra exclusion is needed.
- `iter_media_files` refactored onto the shared predicate — purely mechanical,
  no behaviour change (its tests stay green untouched).

### 2. `main.py` — rebuild from in-run + stored texts

In the per-directory pass, per directory and per engine, before building
`selected`:

- **Census**: `directory_media_files(dir_path, config.extensions,
  config.skip_marker, config.max_age_days)` — the same filters discovery uses,
  so the rebuilt result matches what `--refresh` (which honours them) would
  write.
- **Merge**, keyed by `file_path.name` as today:
  - file processed this run → use the existing in-run `[transcript,
    fixed_or_None]` entry (in-run wins — freshest text for the same file);
  - otherwise `state.get_text(rel, "asr", mtime, size, eng_name)` (and `fixed`
    the same way) → `[asr, fixed_or_None]`; a `None` asr text (never
    transcribed for this engine, back-filled `done` from output existence with
    no stored row, or changed since the text was stored) → **omit** the file
    and collect its name;
  - each surviving entry goes through the same `_pick_summary_input(
    config.dir_summarization.concat_source, …)` per-file fallback as today
    ([main.py:709-717](../src/asr_crawler/main.py#L709)).
- **Empty engine**: if the merged map is empty for an engine, skip writing that
  engine's directory result with one INFO line — no `errors` row, nothing
  failed (`concat_transcriptions`' empty-dict `SummarizationError` invariant is
  preserved by never calling it empty).
- **Omission logging**: when census files were omitted, one WARNING per
  directory+engine naming them, e.g. *"directory result for X [eng] omits 2
  file(s) with no stored text: a.mp3, b.wav"* — the operator can see the result
  is knowingly partial and why (back-filled catalog → `rescan: true`; changed
  file → the next run that processes it re-adds it).
- Everything downstream is unchanged: sorted-filename headers via
  `concat_transcriptions`, the optional LLM summary, `compose`, `write_text`,
  the format pass, `state.clear_errors(scope="dir")`.

### 3. Behaviour that must not change

- **`--refresh`** — already processes every file; the dir pass output is
  identical with or without this epic.
- **Halted run** ([[EPIC-058]]) — the dir pass is still skipped and
  `dir_file_texts` cleared; a rebuild under a halted run would be partial for
  the same reason.
- **`--dry-run`** returns before the dir pass; unaffected.
- **Trigger set** — a directory result is (re)written only for directories
  touched this run, exactly as today; only the *content* now covers the whole
  directory.
- `per_step` vs `per_file` ([[EPIC-042]]) — identical output, as guaranteed.

### 4. Docs

- `CLAUDE.md`: extend the "One consolidated result" Key Conventions bullet —
  a directory result is rebuilt from every current file in the directory
  (this run's texts + stored texts from the index), never just the run's
  subset; note the omission WARNING.
- `docs/architecture/overview.md`: per-directory stage description.
- `docs/architecture/decisions/ADR-012-dir-result-full-rebuild.md` (new): why
  rebuild-from-index over skip-when-partial (a stale-but-correct result beats
  no result, but both lose to the correct one, which the index makes free) and
  over appending to the old result text (composed documents are not
  round-trippable); why direct-children census; why no config knob (this is a
  correctness fix, not a preference).
- `README.md`: one line where directory results are described.

## Files to change

- `src/asr_crawler/file_walker.py` — shared filter predicate + new
  `directory_media_files`.
- `src/asr_crawler/main.py` — census/merge in the per-directory pass, omission
  WARNING, empty-engine skip.
- `CLAUDE.md`, `docs/architecture/overview.md`,
  `docs/architecture/decisions/ADR-012-dir-result-full-rebuild.md`, `README.md`.
- `tasks/backlog.md` — section for this epic added when implementation starts.
- Tests — below.

## Acceptance Criteria

- [x] A file added to a fully-processed directory: the next run's directory
  result contains a block for **every** current file (old ones from stored
  index text, the new one from this run) — no shrinkage to the new file only.
- [x] The rebuilt directory result is byte-identical to what a `--refresh`
  (or from-scratch full run) produces for the same directory state and config.
- [x] `max_files_per_run`-capped batches: after the last capped run the
  directory result covers all files across those runs, not the last subset.
- [x] Census files with no stored text are omitted and named in a WARNING; an
  engine with zero usable texts writes no directory result and records **no**
  `errors` row.
- [x] In-run entries take precedence over stored text for the same file
  (changed file processed this run contributes its new text).
- [x] `concat_source` fallback is per-file as today: a stored-`asr`-only file
  falls back to the original transcript with the existing WARNING.
- [x] Multi-engine ([[EPIC-048]]): each engine's directory result is rebuilt
  from that engine's own stored/in-run texts independently.
- [x] `--refresh`, `--dry-run`, halted-run ([[EPIC-058]]), and
  `processing_mode` behaviour are unchanged.
- [x] No config, schema, or state.py changes; the `iter_media_files` refactor
  is behaviour-neutral (its tests untouched and green).
- [x] Full suite green.

## Tests

- `tests/test_file_walker.py`: `directory_media_files` — media children only,
  honours `skip_marker` / `max_age_days`, sorted, non-recursive (subdirectory
  files not returned), vanished file skipped.
- `tests/test_pipeline/test_dir_rebuild.py` (new):
  - two-run incremental: process `a`, `b`, `c` → add `d` → second run →
    directory result has all four filename headers, sorted; equal to a
    single-run full catalog's result;
  - `max_files_per_run: 1` across two runs → directory result covers `a`+`b`;
  - back-filled `done` file (output exists, no index row) + one new file →
    result contains the new file only + omission WARNING naming the other; no
    `errors` row; run exits cleanly;
  - changed file (mtime/size bump) reprocessed in the same run → new text in
    the directory result;
  - two engines, second added later with no stored texts → only the first
    engine's directory result exists, INFO logged, no error recorded;
  - `concat_source: postprocessed` with mixed fixed/asr-only files → per-file
    fallback visible in the combined text.
- Regression: `test_dir_concat.py`, `test_refresh.py`,
  `test_processing_index.py`, `test_multi_engine.py` pass unchanged.

## Out of Scope

- **Appending to / parsing back the old directory result** — composed
  documents (summary + transcript sections) are not round-trippable; the index
  is the source of truth.
- **Rebuilding untouched directories** — deletion-only changes (a file removed
  from a directory nothing else happened to) and a hand-deleted directory
  result file stay stale until a `--refresh`; the trigger remains "a file in
  this directory was processed this run".
- **Back-filling stored text for a pre-index catalog** — back-filled `done`
  rows have no text by definition ([[EPIC-051]]); `rescan: true` remains the
  remedy and the omission WARNING points at it.
- **Re-queuing `done` files when a new engine is added** — existing
  `is_current` semantics are untouched; the new engine simply has no texts,
  so no directory result until those files are rescanned.
- **A config knob** (e.g. `dir_summarization.rebuild: false` to keep the old
  partial-overwrite behaviour) — writing a knowingly wrong result is not a
  preference worth a switch.
