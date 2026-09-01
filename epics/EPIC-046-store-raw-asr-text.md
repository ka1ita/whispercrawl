# EPIC-046: Store ASR / Post-Processed Text in the Processing Index; Reprocess With `--refresh`

## Goal

Persist each file's raw ASR transcript and its post-processed text **inside the
processing index** (`db/state.db`), keyed to the same row that already tracks
that file's `status` / `steps`. Two payoffs:

1. The raw ASR result — the one slow, expensive, non-deterministic output — is
   never lost, even when the on-disk transcript is post-processed over or
   converted to `.md` / `.html`.
2. A new `whispercrawl --refresh` run re-runs every step *downstream* of ASR
   (post-process → summarize → per-directory concat/summary → format) from the
   stored text, with the current config, and **without a single whisper call**.
   This is the fast path for iterating on the fix prompt, the summary model, or
   the output format.

This epic also removes the need for the `_asr.txt` sidecar floated in the first
draft — the text lives in the DB, not beside the audio (see [[EPIC-047]] for the
broader "keep the audio dir clean" work this feeds).

## Problem Description

The ASR transcription is slow, costly, and non-deterministic; everything
downstream of it is cheap and gets tuned repeatedly. Today none of the
downstream steps can be re-run in isolation:

- `postprocessing.replace_transcription: true` (current [config.yaml](../config.yaml)
  default) moves the fixed text over `<file>.txt`
  ([`main.py:303`](../src/whispercrawl/main.py#L303)) — the raw transcript is
  gone.
- The `formatter` step converts `<file>.txt` → `<file>.md` / `.html` and
  **deletes the `.txt`** ([`formatter.py:89`](../src/whispercrawl/pipeline/formatter.py#L89)),
  so even without `replace_transcription` there is no plain transcript left.
- The only re-run mechanism is `rescan: true`, which re-calls whisper for every
  file. EPIC-041 per-step resume only helps a run that was *interrupted*; a file
  recorded `done` is skipped outright regardless of config changes
  ([`file_walker.py:65`](../src/whispercrawl/file_walker.py#L65)).
- `_diarize.json` (only when `logging.diarize_log: true`, off by default) holds
  raw service JSON but is a debug artifact, not a pipeline input.

## Scope

### 1. `state.py` — text columns on the index

- Bump `SCHEMA_VERSION` to `"3"`. Migration guarded by `PRAGMA table_info(files)`:
  `ALTER TABLE files ADD COLUMN asr_text TEXT` and
  `ALTER TABLE files ADD COLUMN fixed_text TEXT` (both nullable, no default) —
  no-ops on an already-migrated DB, safe against an EPIC-041/043 database.
- `Record` gains `asr_text: Optional[str] = None`, `fixed_text: Optional[str] = None`.
- New methods on `ProcessingState`:
  - `save_text(rel_path, kind, text, mtime, size) -> None` — `kind` ∈
    `{"asr", "fixed"}`. Upsert the matching column together with `mtime`/`size`
    (same row the step tracking uses). Does not change `status` / `steps` /
    `detail`.
  - `get_text(rel_path, kind, mtime, size) -> Optional[str]` — returns the
    stored text only when the row's `mtime`/`size` match the arguments (an
    unchanged file); `None` otherwise. Mirrors `completed_steps` semantics so a
    changed file never reuses stale text.
  - `mark_step`'s existing mtime/size-mismatch reset also nulls `asr_text` /
    `fixed_text` (a new generation invalidates the old text).
- `NullState`: `save_text` no-op, `get_text` always `None`.
- `--refresh` therefore requires `state.enabled: true`; document that.

### 2. `main.py` — write to / read from the index

- `_transcribe_one`: after a successful `transcriber.transcribe()` and the
  `txt_path` write, call `state.save_text(rel, "asr", transcript, mtime, size)`.
  The `"transcribe" in resume_steps` branch reads
  `state.get_text(rel, "asr", ...)` first; only if that is `None` does it fall
  back to reading `txt_path`, and only then to a real transcribe.
- `_postprocess_one`: after a successful `postprocessor.process(...)`, call
  `state.save_text(rel, "fixed", fixed_text, mtime, size)`. The
  `"postprocess" in resume_steps` branch reads `state.get_text(rel, "fixed", ...)`
  before falling back to `fix_path` / `txt_path`.
- New `--refresh` argparse flag. It implies a single pass and never starts the
  scheduler. Branch order in `main()`: `--cleanup` → `--refresh` → `--once` /
  `--dry-run` → scheduler.
- `run_pipeline(config, refresh=True)`:
  - Discover media files with `iter_media_files`'s traversal filters
    (`skip_marker`, `max_age_days`, newest-first, `max_files_per_run`) but with
    the index skip / output-existence check bypassed — every surviving media
    file is a candidate (new `ignore_processed: bool = False` param on
    `iter_media_files`).
  - For each file: `transcript = state.get_text(rel, "asr", mtime, size)`. If
    `None` → log INFO ("no stored ASR text; run a normal pass first") and skip
    (no `_err.txt`). Otherwise build the same per-file context
    `_transcribe_one` returns, with `resume_steps` forced to `set()` so
    `_postprocess_one` / `_summarize_one` genuinely re-run.
  - Reuse `_postprocess_one`, `_summarize_one`, `_finalize_one`, and the
    per-directory concat/summary/format loop unchanged. Honor `processing_mode`.
  - On success, `_finalize_one` records `done` as today; also
    `state.mark_step(rel, s, ...)` for `transcribe` / `postprocess` /
    `file_summarize` so a later normal run treats the file as fully current
    (`transcribe` is legitimately done — the ASR text is in the index).

### 3. `_diarize.json` relocation (small, keeps things consistent)

- When `logging.diarize_log: true`, write the raw JSON under
  `<log_dir>/diarize/<relative-path>.json` instead of beside the audio file, so
  enabling the debug log does not clutter the audio tree. `_transcriber._save_diarize_json`
  takes a base directory from config.

### 4. Config & docs

- `config.py`: no new `transcription` field. Optionally add
  `StateConfig.store_text: bool = True` as an escape hatch (disables the text
  columns → `--refresh` unavailable, smaller DB).
- `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`:
  note in the `state:` comment that the index also stores the raw + fixed
  transcript text to power `--refresh`; document `--refresh` near the schedule
  section.
- `CLAUDE.md` Key Conventions, `docs/architecture/overview.md`,
  `deploy/prod/DEPLOY.md`, `deploy/prod-local/DEPLOY.md`: the index holds the
  ASR/fixed text; `--refresh` re-runs downstream steps from it with no whisper
  call; requires `state.enabled: true`.

## Files to change

- `src/whispercrawl/state.py` — schema v3, text columns, `save_text` /
  `get_text`, `mark_step` reset, `NullState`.
- `src/whispercrawl/main.py` — save/read text, `--refresh` flag + path,
  `mark_step` on refresh success.
- `src/whispercrawl/file_walker.py` — `ignore_processed` param.
- `src/whispercrawl/pipeline/transcriber.py` — `_diarize.json` base dir.
- `src/whispercrawl/config.py` — optional `StateConfig.store_text`;
  `LoggingConfig` diarize dir if needed.
- `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`.
- `CLAUDE.md`, `docs/architecture/overview.md`, `deploy/prod/DEPLOY.md`,
  `deploy/prod-local/DEPLOY.md`.
- Tests — below.

## Acceptance Criteria

- [ ] After a normal run, `state.db` holds the raw ASR transcript and the
  post-processed text for each processed file, keyed to its current
  `mtime`/`size`.
- [ ] `whispercrawl --refresh` re-runs post-processing, per-file summarization,
  per-directory concat/summarization, and formatting for a file already
  recorded `done`, with **zero** whisper service calls.
- [ ] Editing `formatter.speaker_style` / `format` or the fix / summary prompt /
  model, then `--refresh`, regenerates the affected outputs.
- [ ] `--refresh` honors `skip_marker`, `max_age_days`, `max_files_per_run`, and
  `processing_mode`.
- [ ] A file with no stored ASR text is logged and skipped by `--refresh` (no
  `_err.txt`).
- [ ] After a successful `--refresh`, a subsequent normal `run_pipeline` yields
  nothing for that file.
- [ ] A file whose `mtime`/`size` changed since its stored text was written does
  not reuse that text (normal run re-transcribes; `--refresh` skips it).
- [ ] `state.enabled: false` (or `store_text: false`) → no text stored,
  `--refresh` reports it cannot run; normal-run behavior otherwise unchanged.
- [ ] `logging.diarize_log: true` writes under `<log_dir>/diarize/`, not beside
  the audio.
- [ ] All existing `state`, `main`, `config`, `file_walker`, `transcriber`
  tests pass.

## Tests

- `tests/test_state.py`: v2/v3 migration adds `asr_text` / `fixed_text` without
  touching existing rows; `save_text` + `get_text` round-trip; `get_text`
  returns `None` for a mismatched `mtime`/`size` and for an absent row;
  `mark_step` reset nulls the text columns; `NullState` no-ops.
- Pipeline tests: normal run populates the text columns; `--refresh` on a `done`
  file asserts the transcriber mock is **not** called and regenerates `_fix` /
  `_sum` / dir outputs; `speaker_style` change + `--refresh` → new emphasis in
  the `.md`; missing stored text → skipped, no `_err.txt`; post-`--refresh`
  normal run yields nothing; `per_step` and `per_file` `--refresh` produce
  identical on-disk output; changed source file between runs → refresh skips it.
- `tests/test_file_walker.py`: `ignore_processed=True` yields every media file
  regardless of index state / existing outputs, still applying `skip_marker` /
  `max_age_days` / newest-first.
- `tests/test_transcriber.py`: `_diarize.json` written under the configured log
  dir, mirroring the relative path.

## Out of Scope

- **Consolidating the on-disk outputs to one file per audio / per directory** —
  that is [[EPIC-047]]. This epic only moves the *text* into the DB and adds
  `--refresh`; the current sidecar output files (`_fix`, `_sum`, `_all`, …) are
  untouched here.
- **Automatic params-change detection** — hashing the `formatter` /
  `postprocessing` / `*_summarization` config into `meta` and auto-refreshing
  affected files on a normal run. `--refresh` is explicit and ships first.
- **Structured ASR storage (segments / word timestamps).** The stored text is
  the diarized transcript at the current `transcription` settings; changing
  `speaker_timestamps` / `diarize` / `language` / `initial_prompt` still needs a
  real re-transcribe (`rescan: true`). `logging.diarize_log` stays the raw-JSON
  option.
- **Selective refresh** (per file / dir / step). `--refresh` is
  all-downstream-steps over the whole catalog subject to the traversal filters.
- **Resuming an interrupted `--refresh`** — it restarts from the top; per-file
  work is idempotent.
