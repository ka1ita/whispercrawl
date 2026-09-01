# EPIC-041: Per-Step Resume in the Processing Index

## Goal

When a run is interrupted mid-file (crash, restart, `max_files_per_run` cutoff mid-step, `KeyboardInterrupt`), the next run should resume that file from the pipeline step it didn't finish — not re-call the ASR/LLM services for steps that already succeeded and already have their output written to disk.

## Problem Description

EPIC-040's `state.db` records only one status per file — `done` | `error` | `partial` — set once at the *end* of the per-file loop in [`main.py:298`](../src/whispercrawl/main.py#L298). It has no memory of which individual step (transcribe / postprocess / file-summarize) actually completed. Two consequences:

1. **No real resume.** If postprocessing or file-summarization fails or the process is killed after transcription succeeds, the next run re-invokes `transcriber.transcribe()` from scratch for that file — even though `<file>.txt` is already sitting on disk with a good transcript. For a large ASR job this throws away real work on every interruption.

2. **A worse bug: silent false "done".** [`file_walker.py:68-72`](../src/whispercrawl/file_walker.py#L68) back-fills `state.mark(rel, "done", ...)` whenever *any* extension of the transcription output exists on disk — with no check of what `state.lookup(rel)` already says. If transcription succeeded (`<file>.txt` written) but postprocessing then failed and `state.mark(rel, "error", ...)` was recorded, the *next* run's `iter_media_files` finds `<file>.txt` already exists, overwrites the row with `status="done"`, and skips the file forever. The recorded error is silently erased and postprocessing/summarization never run for that file.

## Scope

### 1. `state.py` — per-step tracking

- Bump `SCHEMA_VERSION` to `"2"`. Add a migration: `ALTER TABLE files ADD COLUMN steps TEXT NOT NULL DEFAULT ''` guarded by a `PRAGMA table_info(files)` check so it's a no-op on an already-migrated DB and safe to run against an EPIC-040 database.
- `steps` holds a comma-separated set of step names (`transcribe`, `postprocess`, `file_summarize`) completed for the row's *current* `mtime`/`size` generation.
- `Record` dataclass gains a `steps: str` field.
- New methods on `ProcessingState`:
  - `completed_steps(rel_path, mtime, size) -> set[str]` — returns the recorded step set only when the stored row's `mtime`/`size` match the arguments (unchanged file); returns an empty set for no row, or for a row whose `mtime`/`size` differ (file changed since the last attempt — start over).
  - `mark_step(rel_path, step, mtime, size) -> None` — upsert: if there's no row, or the existing row's `mtime`/`size` don't match, reset `steps` to just `{step}`; otherwise add `step` to the existing set. Sets `status="partial"` and refreshes `updated_at`. Does not touch `detail`.
- `NullState` gets matching no-op methods: `completed_steps(...)` always returns `set()`, `mark_step(...)` does nothing — so `state.enabled: false` reproduces current (no-resume) behavior exactly.

### 2. `main.py` — read back completed steps instead of redoing them

In `_run_pipeline`'s per-file loop ([`main.py:216`](../src/whispercrawl/main.py#L216)), when `config.rescan` is false:

- After `fst = file_path.stat()`, compute `resume_steps = state.completed_steps(rel, fst.st_mtime, fst.st_size)` (empty set when disabled/fresh/changed).
- **Transcribe**: if `"transcribe" in resume_steps` and `txt_path` exists, read `transcript = txt_path.read_text(encoding="utf-8")` instead of calling `transcriber.transcribe()`; log at INFO that the step was resumed. Otherwise transcribe as today, then call `state.mark_step(rel, "transcribe", fst.st_mtime, fst.st_size)` right after the transcript is written.
- **Postprocess**: if `"postprocess" in resume_steps`: when `config.postprocessing.replace_transcription` is true, `fixed_text` is `transcript` as already read from `txt_path` (replace mode overwrites `txt_path` in place, so there is no separate fixed copy — this is documented as an accepted quirk, not fixed). Otherwise read `fixed_text` back from `fix_path` if it exists. Skip calling `postprocessor.process()` in either case. Otherwise postprocess as today, then `state.mark_step(rel, "postprocess", ...)` on success.
- **File summarize**: if `"file_summarize" in resume_steps` and `sum_path` exists, skip `file_summarizer.summarize_file()` but still append `sum_path` to `files_to_format`. Otherwise summarize as today, then `state.mark_step(rel, "file_summarize", ...)` on success.
- The existing end-of-loop `_record(rel, fst, "done"/"error", ...)` call is unchanged — it still governs the `is_current` skip check in `iter_media_files` on the *next* run once every step has succeeded.
- `state.mark_step` is called unconditionally (safe no-op via `NullState` when disabled).

### 3. `file_walker.py` — stop erasing recorded errors

Fix the back-fill branch at [`file_walker.py:69-72`](../src/whispercrawl/file_walker.py#L69):

- Only back-fill `status="done"` from output existence when there is **no existing row at all** for `rel` (`state.lookup(rel) is None`) — i.e. a genuinely un-indexed pre-existing file, matching EPIC-040's original intent.
- A file with an existing row that is not current (`error`, `partial`, or a stale `mtime`/`size`) must always be added to `candidates` regardless of whether some output extension already exists, so `main.py` gets a chance to resume it from `completed_steps`.

### 4. Documentation

- `docs/architecture/overview.md` and `CLAUDE.md` "Key Conventions": add a short note that `state.db` also tracks which pipeline step last completed per file, so an interrupted run resumes mid-file instead of restarting it, and that this fixes the prior false-"done" back-fill quirk.

### 5. Tests

- `tests/test_state.py`: migrating an EPIC-040 `files` table (no `steps` column) adds the column without touching existing rows; `mark_step` accumulates multiple steps for the same unchanged `mtime`/`size`; `mark_step` resets to a single-step set when `mtime`/`size` differ from the stored row; `completed_steps` returns `set()` for an unknown path and for a mismatched `mtime`/`size`; `NullState.completed_steps` always `set()`, `NullState.mark_step` is a no-op.
- `tests/test_file_walker.py`: a file with a recorded `error` row and an existing `.txt` output is still yielded as a candidate (regression test against the false-"done" bug); a file with **no** row and an existing output is still back-filled `done` and skipped (EPIC-040 behavior preserved unchanged).
- Pipeline/integration tests in `tests/test_main_pipeline.py` (or wherever `run_pipeline` is exercised end-to-end): interrupt after transcription (raise from postprocessing on the first invocation) → second `run_pipeline` call does not call the transcriber again for that file, resumes postprocessing and summarization, and ends `done`; interrupt after postprocessing → transcriber and postprocessor are not called again, summarization resumes; touching the source file (new mtime) between attempts discards recorded steps and reprocesses everything.

## Acceptance Criteria

- [x] Interrupting a run after transcription succeeds and re-running does not call the ASR service again for that file.
- [x] Interrupting a run after postprocessing succeeds and re-running does not call the postprocessing LLM prompt again for that file.
- [x] A file whose earlier attempt ended in `error`/`partial` is never silently overwritten with `status="done"` just because an earlier step's output happens to exist on disk.
- [x] A file whose `mtime`/`size` changed since its last recorded attempt reprocesses every step from scratch (no stale step reuse).
- [x] `state.enabled: false` reproduces current (no per-step resume) behavior exactly.
- [x] All existing `state`, `file_walker`, `config`, and `main` tests pass.

## Out of Scope

- Resuming the directory-level concat/summarize/formatter pass if a run is interrupted between the per-file loop finishing and that pass running — it still restarts from scratch on the next run, as today. A candidate for a follow-up epic.
- Resuming a step that was itself interrupted mid-call (e.g. an HTTP request to whisper/ollama cut off partway) — a step is only marked complete after its output file is fully written, so a step killed in flight is simply retried in full; this is intentional, not a gap.
- Concurrent/multi-process runs against one state store (unchanged from EPIC-040).
