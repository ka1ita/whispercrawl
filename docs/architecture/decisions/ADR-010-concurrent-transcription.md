# ADR-010: Concurrent Multi-Engine Transcription

**Date**: 2026-09-02
**Status**: Accepted

## Context

EPIC-048 gave `transcription` an `engines:` list — every engine transcribes
every file and writes its own result. The engines ran strictly sequentially:
`for eng in engines: _transcribe_engine(...)`. A `whisper-asr-webservice`
transcription is minutes per file, so with the two-engine dev stack
(`whisperx` + `gigaam`, separate containers) every file paid
`t_whisperx + t_gigaam` even though the two services could both be working at
once. EPIC-048 and EPIC-054 both listed "run the engines concurrently" as
explicit Out of Scope, deferred to here.

The blockers to simply wrapping the loop in a thread pool:

- **The processing index is one SQLite connection.** `_transcribe_engine` calls
  `state.get_text` / `mark_step` / `save_text` / `record_error`. `sqlite3`
  rejects cross-thread connection use, and concurrent writes on one connection
  are unsafe regardless.
- **Shared dicts.** `dir_file_texts`, `file_engine_ok`, `file_meta`,
  `all_outputs_to_format` are mutated without a lock.
- **`ServiceLogger`** is called from inside `Transcriber.transcribe`.
- **`KeyboardInterrupt`** currently propagates out of the loop and is recorded
  as `status='partial'`; a pool must not swallow it or hang on shutdown.
- **Per-engine failure isolation** (ADR-009) must survive the move into workers.

## Decision

Add `transcription.concurrency: int = 1` (top-level `transcription:` block only,
not merged into per-engine entries; `load_config` rejects `< 1`). It bounds how
many engines' `/asr` calls are in flight at once. `1` = today's exact sequential
path — no `ThreadPoolExecutor` is constructed.

**Only the transcribe HTTP call runs in a worker thread.** `_transcribe_engine`
splits three ways:

- `_prepare_file` / `_prepare_engine` — main thread. Logging, `stat()`,
  `file_meta`, `cleaner.clean_other_formats`, and the index *reads*
  (`completed_steps`, `get_text` for stored ASR). Returns a plain "plan" dict.
- `_transcribe_engine_call(file_path, plan)` — the worker. Pure: reuses the
  stored transcript or calls `transcribers[name].transcribe(file_path)`. No
  index access, no shared-dict mutation. Catches `TranscriptionError` and the
  ADR-009 catch-all and *returns* them as a result dict; lets
  `KeyboardInterrupt` / `SystemExit` propagate.
- `_apply_engine_result(file_path, plan, result)` — main thread. Every index
  *write* (`mark_step`, `save_text`, `record_error`), `file_engine_ok`, and
  `dir_file_texts` population; builds the downstream context dict.

`_run_transcribe_calls(flat)` takes `(file_path, plan)` pairs and, when
`concurrency > 1` and there is more than one pair, runs them through a
`ThreadPoolExecutor(max_workers=min(concurrency, len(flat)))`; otherwise it just
calls the worker in a loop. On `KeyboardInterrupt` / `SystemExit` from
`future.result()` it calls `ex.shutdown(wait=False, cancel_futures=True)` and
re-raises — in-flight requests are abandoned (the process is going down), no
join wait.

**Threads, not `asyncio`.** `httpx.post` is blocking I/O and releases the GIL;
threads are the right tool and `Transcriber` stays synchronous.

**`processing_mode` scoping.** `per_file`: a file's engines fan out, the file
finishes, the next starts — one short-lived pool per file. `per_step`: the
transcribe phase already collects every `(file, engine)` pair before any
post-processing, so a single pool bounds all `/asr` calls across that whole
phase. The later `step_fn` loops are untouched in both modes.

**`--refresh` ignores `concurrency`.** It makes no HTTP call (reads stored text),
so there is nothing to overlap; `concurrency` is forced to `1` on that path.

**`ServiceLogger`** gets a `threading.Lock` around the ndjson write so entries
never interleave.

## Alternatives considered

- **Open the SQLite connection `check_same_thread=False` and guard it with a
  lock.** Rejected — a lock around every index call from the workers is more
  surface area than marshalling the writes back to the one thread that already
  owns the connection, and it invites a future contributor to add an unguarded
  call.
- **A worker per *file* (cross-file parallelism).** Rejected — risks hammering a
  shared single-GPU ASR box and fights `max_files_per_run` / recency ordering.
  Only a file's engines overlap.
- **Parallelise post-processing / summarization too.** Rejected — Ollama serves
  one model at a time; concurrency there just causes model-swap thrash. Same
  call as EPIC-048.
- **`asyncio` + an async `httpx.AsyncClient`.** Rejected — makes `Transcriber`
  async for no gain over threads on a handful of concurrent blocking calls.
- **A single run-wide executor in `per_file` mode.** Rejected — a per-file pool
  is simpler to reason about and its lifetime is bounded; the `per_step` phase
  gets its own single pool because its work is genuinely one batch.
- **Default `concurrency` to the engine count.** Rejected — opt-in. A shared ASR
  host may not want two large models running at once; the operator decides.

## Consequences

- Output — result files, `asr_results` rows, `errors` rows, `--refresh`
  behaviour — is identical regardless of `concurrency`. Only wall-clock changes.
- The SQLite index is only ever accessed from the main thread; no
  `check_same_thread` change, no DB lock.
- Per-engine failure isolation (ADR-009) is unchanged: a worker returns the
  error, `_apply_engine_result` records the `transcribe` row and marks that
  engine failed, the others proceed, the file ends `error`.
- `KeyboardInterrupt` mid-run: pending futures cancelled, in-flight abandoned,
  the file(s) recorded `partial`, the interrupt propagates.
- `deploy/dev/config.yaml` sets `concurrency: 2` (its two engines are the
  motivation). Every other shipped config leaves it commented at `1`.
- New `concurrent.futures` import in `main.py`; `ThreadPoolExecutor` is
  patchable at `whispercrawl.main.ThreadPoolExecutor` for the "no pool when
  sequential" tests.
