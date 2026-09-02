# ADR-009: An Unexpected Exception in a Step Must Not Crash the Run

**Date**: 2026-09-02
**Status**: Accepted

## Context

Each pipeline step caught only its own domain exception — `_transcribe_engine`
caught `TranscriptionError`, `_postprocess_one` `PostProcessingError`,
`_summarize_one` / the per-directory loop `SummarizationError`. Anything else
propagated to `main()` and killed the whole run with a raw traceback.

Observed in the field: `Transcriber.transcribe()` opened the source file with a
bare `open(file_path, "rb")`. A file moved or renamed between `file_walker`
discovery and the transcribe call raised `FileNotFoundError` (a plain `OSError`,
not `TranscriptionError`), which aborted a batch mid-way — every already-written
result was kept, every remaining file was dropped, exit code non-zero, no
`errors` rows for the unprocessed files. The same failure mode existed for a
permission error, a full disk on `result_path.write_text`, a malformed 200-body
from the ASR service, a `compose` / `Formatter` error on bad content.

EPIC-049 / ADR-005 already built the mechanism for "record the failure, keep
going" — an `errors` row plus `status='error'`. It just was not reached for
untyped exceptions.

## Decision

Every per-file / per-engine / per-directory step gets a trailing catch-all in
addition to its typed-exception branch.

- **Ordering** in each step: `except <DomainError>` (nice message, `str(e)`) →
  `except (KeyboardInterrupt, SystemExit)` (record `status='partial'`,
  re-raise) → `except Exception` (`logger.exception`, `_report_error(...,
  repr(e))`, mark the engine/file failed, return). `KeyboardInterrupt` /
  `SystemExit` are not `Exception` subclasses, so the run still aborts cleanly
  on Ctrl-C.
- **`repr(e)`** for the untyped case (not `str(e)`) — an unexpected exception's
  `str()` is often empty (`KeyError`, bare `OSError` subclasses); `repr` always
  carries the type and args. Typed errors keep `str(e)`, which is the
  human-written message.
- **New `step` tokens** in the `errors` table: `finalize` (compose + write of
  the per-file result), `format` (the final `Formatter.format_file` pass),
  `dir_finalize` (compose + write of the per-directory result). No schema
  change — `errors.step` is a free-text column.
- **The loop bodies themselves** are wrapped as a last resort: if an exception
  somehow escapes a step's own guard, `_unexpected_file_failure` records the
  file `status='error'` and the `for file_path in files:` loop continues. The
  per-directory loop and the final formatting pass are wrapped the same way.
- **`Transcriber.transcribe`**: `open()` is wrapped →
  `TranscriptionError("cannot read source file: …")`; the request `except`
  widens from `httpx.RequestError` to `httpx.HTTPError`.
- **`file_walker.iter_media_files`**: the candidate `stat()` is wrapped — a file
  that vanished between `rglob` and `stat` is skipped with a debug log instead
  of the generator raising `OSError`. (This narrows the race window; it does not
  close it — a file can still vanish after the yield, which is why the step
  guard is the real fix.)

## Alternatives considered

- **A pre-flight existence sweep of the whole queue before processing.**
  Rejected — the file can still vanish between the sweep and its transcribe
  call. Catching at the step is the only complete fix; the sweep would just be a
  second place to maintain.
- **Let `_format_diarized` raise `TranscriptionError` on an unparseable 200
  body.** Rejected for now — it already degrades gracefully (returns the raw
  body with a warning) and has a test pinning that; the step catch-all covers a
  genuine crash from response parsing without changing the lenient path.
- **Structured exception storage (type / traceback columns).** Rejected — one
  `repr(e)` string in the existing `message` column is enough to triage; the
  full traceback is in the log via `logger.exception`.
- **Retry / backoff on the failing step.** Out of scope, same as ADR-005 — a
  file with an `errors` row is re-queued on the next run.

## Consequences

- A run over a large catalog always finishes; failures are collected, not fatal.
  `whispercrawl --errors` and the end-of-run WARNING remain the way to see them.
- The only non-`--errors` way for `_run_pipeline` to exit non-zero is
  `KeyboardInterrupt` / `SystemExit`.
- `except Exception` blocks carry `# noqa: BLE001`; the intent (contain, record,
  continue) is the point, not a lint slip.
- No schema bump — `errors.step` gains values, not columns; a pre-EPIC-055 index
  works unchanged.
