# EPIC-055: A Step's Unexpected Exception Must Not Crash the Run

## Goal

Any exception raised while processing one file/engine/step is caught, recorded
in the processing index (an `errors` row + `status='error'`, same as
[[EPIC-049]]), logged, and the run **continues with the next file**. A missing
source file, a permission error, a malformed service response, a full disk on
the result write — none of these should abort a batch that still has hundreds of
files to go. Only `KeyboardInterrupt` / `SystemExit` still propagate (recorded
as `partial` / "interrupted mid-pipeline", as today).

## Problem Description

Each pipeline step catches **only** its own domain exception:

- `_transcribe_engine` catches `TranscriptionError`
  ([main.py:329](../src/whispercrawl/main.py#L329))
- `_postprocess_one` catches `PostProcessingError`
  ([main.py:379](../src/whispercrawl/main.py#L379))
- `_summarize_one` catches `SummarizationError`
  ([main.py:409](../src/whispercrawl/main.py#L409))
- the per-directory loop catches `SummarizationError`
  ([main.py:518](../src/whispercrawl/main.py#L518))

Anything else escapes to `main()` and kills the whole run. Observed:

```
2026-09-02 16:54:24,412 INFO whispercrawl.main: Processing: audio\stalin2\Речь Cталина.mp3
Traceback (most recent call last):
  ...
  File "src/whispercrawl/pipeline/transcriber.py", line 80, in transcribe
    with open(file_path, "rb") as f:
FileNotFoundError: [Errno 2] No such file or directory: 'audio\\stalin2\\Речь Cталина.mp3'
```

`Transcriber.transcribe()` opens the file with a bare `open()`
([transcriber.py:80](../src/whispercrawl/pipeline/transcriber.py#L80)); if the
file was moved/deleted/renamed between discovery and processing (or is locked,
or on an unmounted share), `FileNotFoundError` / `PermissionError` /
`OSError` propagates uncaught. The file that already succeeded
(`audio\stalin\Речь Cталина.mp3`) keeps its result, but every remaining file in
the batch is dropped and the process exits non-zero with a raw traceback.

Other uncaught paths with the same failure mode:

- `httpx` errors not wrapped as `TranscriptionError` (e.g. `httpx.HTTPError`
  subclasses other than `RequestError`), or `response.json()` /
  `KeyError` / `IndexError` while parsing an unexpected ASR response body.
- `result_path.write_text(...)` in `_finalize_one`
  ([main.py:438](../src/whispercrawl/main.py#L438)) and
  `dir_result_path.write_text(...)`
  ([main.py:513](../src/whispercrawl/main.py#L513)) — `OSError` (disk full,
  read-only mount, path too long, encoding surprises).
- `compose(...)` / `formatter.format_file(...)`
  ([main.py:533-535](../src/whispercrawl/main.py#L533-L535)) raising on
  malformed content or a bad `result` / `formatter` config.
- `file_path.relative_to(config.watch_dir)` / `file_path.stat()` edge cases
  beyond the `OSError` already guarded at
  [main.py:288](../src/whispercrawl/main.py#L288).

## Scope

### 1. `pipeline/transcriber.py` — wrap file access

- Guard the `open(file_path, "rb")` (and the `httpx.post` block it wraps) so a
  file-access failure raises `TranscriptionError`:
  ```python
  try:
      f = open(file_path, "rb")
  except OSError as exc:
      raise TranscriptionError(f"cannot read source file: {exc}") from exc
  with f:
      ...
  ```
- Broaden the request `except` from `httpx.RequestError` to `httpx.HTTPError`
  (still → `TranscriptionError`).
- `_format_diarized` already degrades gracefully on an unparseable JSON body
  (returns the raw body + a warning) — left as is; the `main.py` step catch-all
  (§2) covers any genuine crash from response parsing.

### 2. `main.py` — a catch-all around every per-file step

- Add a small helper that runs a step body and turns **any** non-exit exception
  into a recorded error:
  ```python
  def _guard(step: str, ctx_or_rel, *, engine="", scope="file", mtime=None, size=None):
      """context manager: catch KeyboardInterrupt/SystemExit → re-raise;
      catch Exception → logger.exception + _report_error + mark ctx failed."""
  ```
- `_transcribe_engine`: keep the explicit `TranscriptionError` branch (nice
  message), add a trailing `except Exception as e:` that logs with
  `logger.exception(...)`, calls `_report_error(rel, "transcribe", name, repr(e), ...)`,
  sets `file_engine_ok[file_path][name] = False`, and `return None`.
  `except (KeyboardInterrupt, SystemExit)` stays first and re-raises after
  `_record(..., "partial", ...)`.
- `_postprocess_one`, `_summarize_one`: same pattern — domain-exception branch
  plus a catch-all that records the error, sets `ctx["success"] = False`,
  and returns.
- `_finalize_one`: wrap `compose(...)` + `write_text(...)` in a
  `try/except Exception` → `_report_error(rel, "finalize", eng, ...)`,
  `file_engine_ok[file_path][eng] = False`; do **not** append a half-written
  path to `all_outputs_to_format`.
- Per-directory loop: broaden `except SummarizationError` to also catch
  `Exception` for `compose` / `write_text` (record `step="dir_summarize"` or a
  new `step="dir_finalize"`, `scope="dir"`).
- Final formatting pass ([main.py:533](../src/whispercrawl/main.py#L533)): wrap
  each `formatter.format_file(path)` in `try/except Exception` → `logger.error`
  (a formatting failure on one file must not skip the rest); record an
  `errors` row (`step="format"`) keyed to that path.
- Top of `_run_pipeline` file loop: if a completely unexpected exception escapes
  a step guard anyway, the `for file_path in files:` body is itself wrapped so
  one pathological file cannot abort the loop — `logger.exception`, best-effort
  `_record(rel, fst, "error", ...)`, `continue`.

### 3. `file_walker.py` — tolerate a file that vanished before yield

- `iter_media_files` already `stat()`s candidates; if a candidate disappears
  between the directory scan and the yield, skip it with a `logger.debug`
  instead of letting `OSError` escape the generator.

### 4. `state.py`

- No schema change. `record_error` already accepts arbitrary `step` strings;
  document the new tokens (`finalize`, `dir_finalize`, `format`) in the
  `errors.step` comment.

### 5. Docs

- `CLAUDE.md` Key Conventions / pipeline description: state explicitly that
  **any** exception in a step (not just the typed pipeline errors) is recorded
  in the index and the run continues; only Ctrl-C aborts.
- `docs/architecture/overview.md`: pipeline failure table — "on any exception".
- `docs/architecture/decisions/ADR-009-resilient-step-failures.md`: catch-all
  vs. typed-only; why `repr(e)` for the unexpected case; why the file loop
  itself is guarded.

## Files to change

- `src/whispercrawl/pipeline/transcriber.py` — wrap `open`, broaden `httpx`
  catch, guard response parsing.
- `src/whispercrawl/main.py` — `_guard` helper / catch-all `except Exception`
  in `_transcribe_engine`, `_postprocess_one`, `_summarize_one`,
  `_finalize_one`, the per-dir loop, the final formatting pass, and the
  top-level file loop.
- `src/whispercrawl/file_walker.py` — skip a vanished candidate.
- `src/whispercrawl/state.py` — `errors.step` comment only.
- `CLAUDE.md`, `docs/architecture/overview.md`,
  `docs/architecture/decisions/ADR-009-resilient-step-failures.md`.
- Tests — below.

## Acceptance Criteria

- [x] A source file deleted between discovery and transcription records one
  `errors` row (`step='transcribe'`, message mentions the file) and
  `status='error'`; **every subsequent file in the batch is still processed**;
  the process exits 0 (errors are surfaced by the end-of-run WARNING and
  `--errors`, not by a crash).
- [x] `PermissionError` / generic `OSError` opening the source behaves the same
  (`open()` wrapped → `TranscriptionError`; any exception type contained).
- [x] Response-parsing crash on a 200 body is contained by the step catch-all;
  `_format_diarized`'s existing lenient "raw body + warning" path is unchanged.
- [x] `write_text` raising `OSError` in `_finalize_one` records a `finalize`
  error, writes no partial result beside the audio, other files continue.
- [x] A `formatter.format_file` failure on one output logs an error and records a
  `format` row; the remaining outputs are still formatted.
- [x] A directory-loop `compose` / `concat` / `write_text` failure records a
  `scope='dir'` `dir_finalize` row and does not abort the remaining directories.
- [x] `KeyboardInterrupt` still propagates and records `status='partial'`
  ("interrupted mid-pipeline") — unchanged.
- [x] The next run (or `--refresh`) after the underlying cause is fixed clears
  the `errors` rows on success (existing EPIC-049 behavior, unchanged).
- [x] All existing `main`, `transcriber`, `file_walker`, `state` tests pass
  (460 passing).

## Tests

- `tests/test_transcriber.py`: `transcribe()` on a non-existent path →
  `TranscriptionError` (not `FileNotFoundError`); on a path that 200s with body
  `"not json"` → `TranscriptionError`; `httpx.ConnectError` → `TranscriptionError`.
- `tests/test_main.py` (or the pipeline integration test):
  - two files queued, the first removed from disk before its transcribe call →
    first gets an `errors` row + `status='error'`, second file's result is
    written, run exits 0;
  - monkeypatch `Path.write_text` to raise `OSError` for one file → `finalize`
    error row, no result file, other file unaffected;
  - monkeypatch `Formatter.format_file` to raise for one path → error logged,
    other paths formatted;
  - monkeypatch `compose` to raise inside the dir loop → `scope='dir'` row,
    next directory still processed.
- `tests/test_file_walker.py`: a candidate deleted between scan and `stat` is
  skipped, no exception, other candidates yielded.

## Out of Scope

- **Retry / backoff** for the failing step (still [[EPIC-049]] out-of-scope).
- **Structured exception storage** (type / traceback columns) — `repr(e)` in the
  existing `message` column is enough.
- **A pre-flight existence sweep** of the whole queue before processing — the
  race window still exists for long runs; catching at the step is the fix.
- **Distinguishing "file vanished" from "file locked"** in the index — both are
  one `transcribe` error row with the OS message.
