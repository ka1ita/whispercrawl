# EPIC-042: Configurable Processing Mode (Per-File vs Per-Step)

## Goal

Let an operator choose the order pipeline work happens in for a run:

- **`per_file`** (current, default behavior): every step (transcribe → postprocess → file-summarize) runs for one file before moving to the next file.
- **`per_step`** (new): a step runs across *all* pending files before the next step starts — transcribe every file, then postprocess every file, then file-summarize every file.

## Problem Description

`postprocessing` and `file_summarization` are independently configurable `OllamaStepConfig`s ([`config.py:39`](../src/whispercrawl/config.py#L39)) and commonly point at **different** Ollama models (a fast correction model vs. a larger summarization model). In today's per-file loop ([`main.py:216`](../src/whispercrawl/main.py#L216)), a single pass over N files calls postprocess-model then summarize-model, alternating **N times** — Ollama has to swap the loaded model on (up to) every file. For a large batch this swap cost dominates wall-clock time.

Running each step across the whole batch instead — all transcriptions, then all postprocessing, then all summarization — means Ollama loads the postprocessing model once, processes every file, then loads the summarization model once. It also gives an operator a natural checkpoint to skim all raw transcripts before spending LLM time correcting/summarizing them.

Neither mode should change *what* gets written — same output files, same content, same `state.db` step-tracking from [EPIC-041](EPIC-041-per-step-resume.md) — only the *order* work happens in within a run.

## Scope

### 1. `config.py`

- Add `processing_mode: str = "per_file"` to `Config` ([`config.py:105`](../src/whispercrawl/config.py#L105), beside `rescan`).
- `load_config` validates it against `("per_file", "per_step")`, raising `ValueError` otherwise (same pattern as `formatter.format` validation at [`config.py:135`](../src/whispercrawl/config.py#L135)).

### 2. `main.py` — extract per-file, per-step logic into reusable functions

Refactor the body of the current per-file loop ([`main.py:216`](../src/whispercrawl/main.py#L216)-[`main.py:328`](../src/whispercrawl/main.py#L328)) into three functions closing over the shared run context (`transcriber`, `postprocessor`, `file_summarizer`, `state`, `config`, `dir_file_texts`, error/resume helpers) so both modes call the *same* code instead of duplicating it:

- `_transcribe_one(file_path) -> TranscribeResult` — resume-or-call-transcriber, write `.txt`, `mark_step`, populate `dir_file_texts`. On `TranscriptionError`, writes the error file, records `state` `error`, and returns a failure marker (no further steps run for this file, in either mode).
- `_postprocess_one(file_path, transcript) -> PostprocessResult` — resume-or-call-postprocessor, write `_fix.txt` (or replace `.txt`), `mark_step`. On `PostProcessingError`, writes the error file and returns failure — this does **not** exclude the file from summarization (matches current fallback behavior in `_pick_summary_input`, [`main.py:14`](../src/whispercrawl/main.py#L14)).
- `_summarize_one(file_path, transcript, fixed_text) -> SummarizeResult` — resume-or-call-summarizer, write `_sum.txt`, `mark_step`. On `SummarizationError`, writes the error file and returns failure.

Each returns whether its step succeeded and accumulates its output path into `all_outputs_to_format`; none of them call `cleaner.clean(...)` or the final `state.mark(..., "done"/"error", ...)` — that stays a per-file finalization step (`_finalize_one(file_path, fst, rel, overall_success)`) called once per file after all its steps are known, in both modes.

- **`per_file` mode**: unchanged control flow — `for file_path in files: t = _transcribe_one(...); if t.failed: continue; p = _postprocess_one(...); s = _summarize_one(...); _finalize_one(...)`.
- **`per_step` mode**: three passes over `files` — `{f: _transcribe_one(f) for f in files}`, then `{f: _postprocess_one(f, ...) for f in survivors}`, then `{f: _summarize_one(f, ...) for f in survivors}` (`survivors` = files whose transcription succeeded) — followed by one `_finalize_one(...)` pass over `survivors`.

Directory-level concat/summarization ([`main.py:329`](../src/whispercrawl/main.py#L329) onward) and the final `Formatter` pass are unchanged and mode-agnostic — both feed off the same `dir_file_texts` / `all_outputs_to_format` regardless of which mode populated them.

### 3. `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`

Add near `rescan`:

```yaml
# "per_file" (default): every step runs on one file before moving to the next.
# "per_step": each step runs across all pending files before the next step starts —
# reduces Ollama model-swap overhead when postprocessing and file_summarization use
# different models.
processing_mode: per_file
```

### 4. Documentation

- `docs/architecture/overview.md`: document both modes and the model-swap rationale.
- `CLAUDE.md` "Key Conventions": one line noting the config option and default.

### 5. Tests

- `tests/test_config.py`: `processing_mode` defaults to `"per_file"`; invalid value raises `ValueError`.
- `tests/test_processing_mode.py` (new), patching `transcriber.transcribe` / `postprocessor.process` / `summarizer.summarize_file` to record call order:
  - `per_file` (default) over N files → call order is `transcribe(a), postprocess(a), summarize(a), transcribe(b), postprocess(b), summarize(b), ...` (regression: byte-identical to current behavior).
  - `per_step` over N files → call order is `transcribe(a), transcribe(b), postprocess(a), postprocess(b), summarize(a), summarize(b)`.
  - `per_step`, transcription fails for one file → that file is excluded from the postprocess and summarize passes; other files are unaffected; failed file's error file is written.
  - `per_step`, postprocessing fails for one file → that file **is still summarized** (using the original transcript, matching `summarize_source` fallback); other files unaffected.
  - Both modes produce identical on-disk output (same files, same content, same dir-summary/concat) for the same input set — order is the only difference.
  - `per_step` mode respects `state.completed_steps` the same way `per_file` does: a file with `"transcribe"` already recorded is skipped in the transcribe pass but still included in the postprocess/summarize passes.
  - `max_files_per_run` and `rescan` behave identically under both modes (slicing/cleanup happen before the mode branch).

## Acceptance Criteria

- [x] `processing_mode: per_file` (default) is behaviorally identical to pre-epic output and call order.
- [x] `processing_mode: per_step` transcribes every pending file before postprocessing any of them, and postprocesses every survivor before summarizing any of them.
- [x] A transcription failure in `per_step` mode excludes only that file from later steps; other files proceed normally.
- [x] A postprocessing failure in `per_step` mode does not prevent that file from being summarized.
- [x] Both modes write identical output files (content and paths) for the same input and config, aside from step ordering.
- [x] Per-step resume (EPIC-041) works correctly in both modes.
- [x] Invalid `processing_mode` values raise `ValueError` at config load.
- [x] All existing tests pass.

## Out of Scope

- Actual parallelism/concurrency within a step's batch (e.g. transcribing multiple files at once) — `per_step` only changes ordering, not concurrency.
- Auto-detecting when `per_step` would help (e.g. only enabling it automatically when postprocessing/summarization models differ) — this is an explicit operator choice.
- Directory-level (concat/summary) or Formatter-pass batching changes — already batch across all files regardless of mode and are untouched.
