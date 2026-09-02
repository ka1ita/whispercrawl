# EPIC-056: Concurrent Multi-Engine Transcription

**Status**: Landed 2026-09-02. See [ADR-010](../docs/architecture/decisions/ADR-010-concurrent-transcription.md).

## Goal

When `transcription.engines` lists more than one ASR endpoint, send a file's
`/asr` request to **every engine at once** instead of one after another, so the
transcribe step's wall-clock cost per file is the *slowest* engine rather than
the *sum* of all engines.

A new `transcription.concurrency` knob (int, default `1`) bounds how many engine
requests may be in flight at the same time. `concurrency: 1` keeps today's exact
sequential behaviour and code path — no thread pool, no ordering change.

Only the **transcribe step** (the HTTP call to `whisper-asr-webservice`) runs in
parallel. Post-processing, summarization, compose/format, and the per-directory
pass stay sequential and single-threaded — they hit Ollama, which serves one
model at a time, so concurrency there only causes model-swap thrash (explicit
Out of Scope of [[EPIC-048]], unchanged here).

## Depends on

[[EPIC-048]] (landed) — `transcription.engines`, per-engine contexts, per-engine
index rows and result files. This epic parallelises the loop EPIC-048 introduced
(`for eng in engines: _transcribe_engine(...)` in
[`_transcribe_file`](../src/whispercrawl/main.py#L281)) and changes nothing about
what each engine produces.

Related: [[EPIC-054]] (dev two-engine stack — the first real consumer of this),
[[EPIC-042]] (`processing_mode` — interacts, see below),
[[EPIC-055]] (resilient step failures — per-engine error isolation must survive
the move into worker threads),
[[EPIC-040]] (processing index / SQLite — thread-safety of `state` writes).

## Problem Description

`whisper-asr-webservice` transcription is minutes-per-file, dominated by the
model inference on the ASR side. With two engines (`whisperx` + `gigaam` in the
dev stack) every file pays `t_whisperx + t_gigaam` even though the two services
are separate containers/hosts that could both be working at once. On a catalog
of any size the second engine roughly doubles a run.

Today's call site, in `_transcribe_file`:

```python
contexts = []
for eng in engines:
    ctx = _transcribe_engine(file_path, rel, fst, eng)
    if ctx is not None:
        contexts.append(ctx)
return contexts
```

`_transcribe_engine` does, in order: resolve resume state, read stored ASR text
(`state.get_text`), **call `transcribers[name].transcribe(file_path)`** (the slow
HTTP call), then on success mutate shared state — `state.mark_step`,
`state.save_text`, `dir_file_texts[...]`, `file_engine_ok[...]` — and return a
context dict.

Blockers to just wrapping that loop in a `ThreadPoolExecutor`:

1. **`state` is SQLite over one connection.** `sqlite3` connections reject
   cross-thread use unless opened `check_same_thread=False`, and even then
   concurrent writes on one connection are not safe. `state.get_text` /
   `mark_step` / `save_text` are called from inside `_transcribe_engine`.
2. **Shared dict mutation.** `dir_file_texts`, `file_engine_ok`, `file_meta`,
   `all_outputs_to_format` are plain dicts/lists mutated without a lock.
3. **`ServiceLogger`** (`svc_log.log(...)`) is called from `Transcriber.transcribe`
   — its file/stream writes must tolerate concurrent callers.
4. **`_report_error`** writes an `errors` row via `state` — same as (1).
5. **`KeyboardInterrupt` / `SystemExit`** currently propagate out of the loop and
   are turned into a `partial` record. With a pool, in-flight futures must be
   cancelled / abandoned and the interrupt re-raised.
6. **Per-engine failure isolation** ([[EPIC-055]]): one engine raising must still
   record its own `errors` row and leave the other engines' results intact.

## Design

### Keep the network call in the worker; marshal all shared-state writes back to the main thread

`_transcribe_engine` splits into:

- **`_transcribe_engine_call(file_path, rel, fst, eng) -> EngineResult`** — pure,
  thread-safe, no `state` writes, no shared-dict mutation. Does: language detect,
  resume-step lookup is passed *in* (computed on the main thread before submit),
  read of `stored_asr` is passed *in* too, then either returns the stored text or
  performs `transcribers[name].transcribe(file_path)`. Catches `TranscriptionError`,
  `Exception`, and lets `KeyboardInterrupt`/`SystemExit` propagate. Returns a
  small result object: `{engine, ok, transcript|None, error:(step,msg)|None,
  from_stored:bool}`.
- **`_apply_engine_result(file_path, rel, fst, eng, result)`** — runs on the main
  thread after the future resolves. Does exactly what the old function's tail did:
  `state.mark_step` + `state.save_text` on success (skip when `from_stored`),
  `_report_error` + `file_engine_ok[...] = False` on failure, populate
  `dir_file_texts` and build/append the context dict.

`_transcribe_file` becomes:

```python
prepared = [_prepare_engine(file_path, rel, fst, eng) for eng in engines]
# _prepare_engine reads resume_steps + stored_asr on the main thread (state reads),
# returns everything the worker needs.

if concurrency <= 1 or len(prepared) <= 1:
    results = [_transcribe_engine_call(p) for p in prepared]
else:
    with ThreadPoolExecutor(max_workers=min(concurrency, len(prepared))) as ex:
        futs = {ex.submit(_transcribe_engine_call, p): p for p in prepared}
        results = [f.result() for f in _ordered(futs)]   # re-raises KI/SE

contexts = []
for p, r in zip(prepared, results):
    ctx = _apply_engine_result(file_path, rel, fst, p.eng, r)
    if ctx is not None:
        contexts.append(ctx)
return contexts
```

With this shape `state` is only ever touched from the main thread, so no
`check_same_thread` change and no DB lock. The only thing genuinely running in
parallel is `httpx.post` inside `Transcriber.transcribe` (blocking I/O — the GIL
is released, threads are the right tool; no `asyncio`).

### `ServiceLogger` thread-safety

Audit `ServiceLogger.log`. If it appends to a list / writes a line per call, guard
the mutation/write with a `threading.Lock` (cheap, only contended when >1 engine
finishes a request at the same instant). Document the guarantee in its docstring.

### Config

`TranscriptionConfig.concurrency: int = 1` (top-level block only, alongside
`engines`; not merged into per-engine entries). `load_config`:

- default `1`;
- `raw["transcription"].get("concurrency", 1)`;
- `ValueError` if `< 1`;
- value above `len(engines)` is allowed (clamped at use — harmless).

`concurrency: 1` (or a single engine, or no `engines:` list) ⇒ the sequential
branch, byte-for-byte today's behaviour.

### `processing_mode` interaction

- **`per_file`** (default): concurrency is *within* one file — its engines fan
  out, the file completes, the next file starts. Simple, bounded, matches the
  mental model. This is the whole epic.
- **`per_step`**: the transcribe phase already collects `(file, engine)` pairs
  across *all* files before any post-processing. Here `concurrency` bounds the
  total number of in-flight `/asr` calls across that whole phase (a single
  `ThreadPoolExecutor(max_workers=concurrency)` over every pair). Still only the
  transcribe phase; the later `step_fn` loops are untouched.

### Interrupt handling

`_ordered(futs)` collects results; if `f.result()` raises `KeyboardInterrupt` /
`SystemExit`, cancel the not-yet-started futures, let the `with ThreadPoolExecutor`
block exit (in-flight requests are abandoned — `httpx` will be interrupted or
finish and be discarded), record `partial` for the file (as today), and re-raise.
No new swallowing of interrupts.

### What does NOT change

- Per-engine result files, index rows, `--refresh` semantics, `--cleanup`,
  `diarize/<engine>/` JSON, `max_files_per_run` (counts files), `--errors`.
- Output is **identical** regardless of `concurrency` — only wall-clock differs.
- `--refresh` does no HTTP call; its per-engine loop can stay sequential (nothing
  to overlap) — `concurrency` is ignored on the refresh path. State that
  explicitly.
- Single-engine / no-`engines:` runs: no executor is ever created.

## Files to change

- `src/whispercrawl/config.py` — `TranscriptionConfig.concurrency`; `load_config`
  parse + `>= 1` validation; keep it off the per-engine merge.
- `src/whispercrawl/main.py` — split `_transcribe_engine` into
  `_prepare_engine` / `_transcribe_engine_call` (pure) /
  `_apply_engine_result` (main-thread); thread-pool fan-out in `_transcribe_file`
  for `per_file`; thread-pool over `(file, engine)` pairs in the `per_step`
  transcribe phase; interrupt-safe result collection.
- `src/whispercrawl/pipeline/logging_service.py` (or wherever `ServiceLogger`
  lives) — lock around the shared write; docstring note.
- `config.yaml`, `deploy/dev/config.yaml`, `deploy/prod/config.yaml`,
  `deploy/prod-local/config.yaml` — commented `concurrency:` under
  `transcription:` (dev config: set it to `2`, its two engines are the reason
  this exists).
- `CLAUDE.md` — Key Conventions "Multiple ASR engines" bullet: note engines
  transcribe concurrently when `transcription.concurrency > 1`, downstream stays
  sequential.
- `docs/architecture/overview.md` — transcribe step / multi-engine description.
- `docs/architecture/decisions/ADR-010-concurrent-transcription.md` (new) —
  threads-not-async, main-thread-only `state`, transcribe-only, opt-in knob
  defaulting to sequential, `per_file` vs `per_step` scoping.
- `epics/EPIC-048-multiple-asr-engines.md` — one-line note that the "Concurrent
  transcription" Out-of-Scope item is delivered by EPIC-056.
- `tasks/backlog.md` — task checklist.

## Acceptance Criteria

- [x] `transcription.concurrency` defaults to `1`; `load_config` raises
  `ValueError` for `0` / negative; a value `>` engine count loads fine.
- [x] With `concurrency: 1` the transcribe path is the existing sequential loop
  (no `ThreadPoolExecutor` constructed — assertable via a patch/spy), and output
  + index rows are byte-identical to pre-epic for a two-engine run.
- [x] With `concurrency: 2` and two engines whose fake transcribers each sleep
  `d`, one file's transcribe step wall-clock is `~d`, not `~2d` (timing test with
  generous margin).
- [x] Two-engine, `concurrency: 2`: on-disk results, `asr_results` rows, and
  `errors` rows are identical to the same run at `concurrency: 1`.
- [x] One engine's transcriber raising `TranscriptionError` (and, separately, a
  bare `RuntimeError`) under `concurrency: 2` records that engine's `errors` row
  with `step='transcribe'`, leaves the other engine's result + index row intact,
  and the file is recorded `error` (not `done`) — [[EPIC-055]] behaviour
  unchanged under threading.
- [x] `state` (SQLite) is only accessed from the main thread — no
  `check_same_thread=False`, no cross-thread connection use (code review + a test
  that would trip `sqlite3`'s thread check if violated).
- [x] `ServiceLogger` under concurrent `.log(...)` calls produces well-formed,
  non-interleaved entries (test hammering it from N threads).
- [x] `KeyboardInterrupt` raised by one engine's transcriber mid-run: the run
  stops, the file is recorded `partial`, the interrupt propagates (no hang on
  executor shutdown, generous test timeout).
- [x] `processing_mode: per_step` with `concurrency: 3` over 4 files × 2 engines:
  at most 3 `/asr` calls in flight at once (instrumented fake), output identical
  to `per_step` + `concurrency: 1`.
- [x] `--refresh` ignores `concurrency` (no executor), regenerates each engine
  from stored text as before.
- [x] Single implicit engine (no `engines:` list) with any `concurrency` value:
  no executor, behaviour unchanged.
- [x] `deploy/dev/config.yaml` sets `concurrency: 2`; `docker compose … config`
  and `whispercrawl --config deploy/dev/config.yaml --once --dry-run` still load
  clean.
- [x] Full suite green; `ruff check src tests` clean.

## Out of Scope

- **Concurrency across *files*** (a worker per file). Only a file's engines
  overlap. Cross-file parallelism risks hammering a shared single-GPU ASR box and
  interacts badly with `max_files_per_run` ordering / recency priority.
- **Parallel post-processing / summarization / dir pass.** Ollama is one model at
  a time — unchanged from [[EPIC-048]].
- **`asyncio` / an async httpx client.** Blocking `httpx.post` in threads is
  sufficient and keeps `Transcriber` synchronous.
- **A global/shared executor across the whole run** in `per_file` mode. One
  short-lived pool per file; the `per_step` phase gets its own single pool.
- **Per-engine concurrency weighting / priority / rate-limiting** beyond the
  single `max_workers` bound.
- **Retry / backoff on a failed engine.** Failure handling is exactly [[EPIC-055]].
- **Making `state` writes concurrent** (WAL multi-connection, a writer thread).
  The marshal-to-main-thread design deliberately avoids needing it.
