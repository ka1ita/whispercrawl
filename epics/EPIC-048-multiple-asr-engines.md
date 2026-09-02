# EPIC-048: Multiple ASR Engines — Parallel Transcription, Per-Engine Results

## Goal

Let one whispercrawl run send every audio file to **more than one ASR
endpoint** (a different `whisper-asr-webservice` deployment, engine, or
parameter set) and keep the outputs side by side so they can be compared.

After this epic, `transcription` accepts an `engines:` list. Each engine:

- transcribes every file independently,
- has its **raw + post-processed text stored in the processing index**, keyed
  by engine (extends [[EPIC-046]]),
- produces its **own result file per audio file and per directory**
  (extends [[EPIC-047]]): `meeting_<engine>.<ext>`, `_<dirname>_<engine>.<ext>`.

With no `engines:` list configured, behavior and output filenames are exactly
as today (single implicit engine, empty label, no `_<engine>` segment).

## Problem Description

`transcription` is a single `TranscriptionConfig` with one `url`
([config.py:25](../src/whispercrawl/config.py#L25)). A run can only talk to one
ASR service with one engine and one parameter set. Evaluating a second engine
(e.g. `faster_whisper` vs `whisperx`), a newer model, or a different
`initial_prompt` means editing config, doing a full `rescan: true` run, saving
the outputs elsewhere, reverting, and running again — and the index
([[EPIC-046]]) only has room for one `asr_text` / `fixed_text` per file, so the
first result is overwritten.

Downstream, `_transcribe_one` / `_postprocess_one` / `_summarize_one` and the
per-directory concat/summary loop in [main.py](../src/whispercrawl/main.py) all
assume a single transcript per file, and output filenames
([`output_path`](../src/whispercrawl/main.py#L28)) have no engine dimension.

## Scope

Depends on [[EPIC-046]] (landed) and [[EPIC-047]] (composed single result per
file/dir) — this epic adds the engine dimension to both. If EPIC-047 has not
landed when this is implemented, apply the same `_<engine>` segment to the
current sidecar names (`_fix` / `_sum` / `_all`) instead.

### 1. `config.py` — engine list

```python
@dataclass
class TranscriptionConfig:
    name: str = ""            # engine label: filename segment + index key; "" = single implicit engine
    url: str = "http://localhost:9000"
    language: str = "auto"
    diarize: bool = False
    # ... existing fields unchanged ...
    engines: List["TranscriptionConfig"] = field(default_factory=list)  # only meaningful on the top-level block
```

- `engines` is parsed only from the top-level `transcription:` block. Each list
  entry is merged **onto a copy of the top-level block** (entry values win,
  unset fields inherit) so shared settings (`timeout`, `diarize`,
  `speaker_timestamps`, …) are written once. `engines` itself is not inherited.
- `load_config` resolves `transcription` into `config.transcription.engines`
  as a non-empty `List[TranscriptionConfig]`:
  - no `engines:` key → `[<the top-level block with name="">]`.
  - `engines:` present → one merged `TranscriptionConfig` per entry; the
    top-level block supplies defaults only (it is not itself an engine).
- Validation in `load_config`:
  - every engine `name` matches `^[A-Za-z0-9._-]+$` (filename-safe) — empty
    name allowed **only** when there is exactly one engine and no `engines:`
    list;
  - engine `name`s are unique;
  - `output_suffix` / `error_suffix` still come from the (base) block.
- Add a helper `engine_label(name)` → `f"_{name}"` when `name` else `""`, used
  everywhere a filename segment or index key is built.

### 2. `state.py` — per-engine text + step tracking

EPIC-046 stores one `asr_text` / `fixed_text` column on `files`. Generalize to
an engine-keyed side table.

- Bump `SCHEMA_VERSION` to `"4"`.
- New table:
  ```sql
  CREATE TABLE IF NOT EXISTS asr_results (
      path   TEXT NOT NULL,
      engine TEXT NOT NULL,
      kind   TEXT NOT NULL,          -- 'asr' | 'fixed'
      text   TEXT,
      mtime  REAL,
      size   INTEGER,
      PRIMARY KEY (path, engine, kind)
  );
  ```
- Migration (guarded by `PRAGMA table_info`): copy existing
  `files.asr_text` / `files.fixed_text` into `asr_results` with `engine=''`
  (kind `asr` / `fixed`), keyed to that row's `mtime` / `size`. Leave the old
  columns in place but stop reading/writing them (SQLite `DROP COLUMN` needs
  3.35+; a follow-up can drop them).
- `save_text(rel_path, kind, text, mtime, size, engine="")` — upsert into
  `asr_results`.
- `get_text(rel_path, kind, mtime, size, engine="")` — return the row's text
  only when `mtime` / `size` match; `None` otherwise.
- Step tracking gains an engine dimension. `steps` on `files` stays a single
  set; step tokens for a named engine are suffixed: `transcribe`,
  `transcribe:whisperx`, `postprocess:whisperx`, `file_summarize:whisperx`
  (empty engine → bare token, unchanged). `mark_step` / `completed_steps` take
  `engine=""`.
- A file's `files.status` becomes `done` only once **every** configured engine
  has finished; `error` if any engine errored (detail names the engine). The
  mtime/size-mismatch reset in `mark_step` also deletes that file's
  `asr_results` rows (all engines) and clears all step tokens.
- `NullState`: new signatures as no-ops (`get_text` → `None`).

### 3. `main.py` — per-engine pipeline

- Build one `Transcriber` per engine from `config.transcription.engines`
  (existing constructor, merged `TranscriptionConfig`). Diarize-log dir per
  [[EPIC-046]] gets an `<engine>/` segment when named, so JSON from different
  engines does not collide.
- `_transcribe_one(file_path)` → `_transcribe_file(file_path)` returning a
  **list of per-engine contexts**, each `{engine, transcript, rel, fst,
  resume_steps, ...}`. Per engine:
  - `resume_steps = state.completed_steps(rel, mtime, size, engine)`;
  - stored-ASR reuse (`refresh` / resume) reads
    `state.get_text(rel, "asr", mtime, size, engine)`;
  - on a real transcribe, `state.save_text(rel, "asr", transcript, mtime,
    size, engine)`.
- `_postprocess_one` / `_summarize_one` / `_finalize_one` take a single
  per-engine ctx and thread `engine` through every `output_path`,
  `state.save_text`, `state.mark_step`, and error-file call. Result / composer
  filenames: `output_path(file_path, engine_label(engine) + suffix, fmt)` (with
  EPIC-047, `suffix` is `""` for the file result → `meeting_whisperx.<ext>`).
- Error file is per engine: `meeting_<engine>_err.txt`. One engine failing does
  not stop the others or the directory step for the engines that succeeded.
- Processing order:
  - `per_file`: for each file → for each engine → transcribe, postprocess,
    summarize, finalize.
  - `per_step`: for each step → for each (file, engine).
- `_finalize_one` marks the file `done` only when all engines for that file
  have finalized without error (the state layer already enforces this — call
  `mark_done` after the last engine).

### 4. `main.py` — per-directory, per engine

- `dir_texts` becomes `dir_texts[engine][filename] = text`.
- After the file loop, for each engine independently: build the concat
  (`concat_transcriptions`), optionally the dir summary, compose (EPIC-047),
  and write `_<dirname><engine_label>.<ext>` (respecting
  `dir_summarization.underscore_prefix`). Dir error file
  `_<dirname>_<engine>_err.txt`.

### 5. `--refresh`

- Loops engines exactly like a normal run. Per file per engine:
  `state.get_text(rel, "asr", mtime, size, engine)` → `None` logs INFO and
  skips **that engine** (other engines still refresh). `resume_steps` forced
  empty so postprocess / summarize genuinely re-run. On success `mark_step`
  for that engine so a later normal run treats it current.

### 6. Cleanup

- `run_cleanup` / `pipeline/cleaner.py`: for every configured engine, remove
  `<stem><engine_label><suffix>.<ext>` (all `cleanup.targets` suffixes) and the
  per-engine error / dir files. The empty-engine case is unchanged.
- `clean_other_formats` (EPIC-029) likewise iterates engines.

### 7. Config files

- `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`:
  keep the flat `transcription:` block as the shared base; add a **commented**
  `engines:` example:
  ```yaml
  transcription:
    url: ${WHISPER_URL:http://localhost:9000}
    language: ru
    diarize: true
    speaker_timestamps: true
    timeout: 3600
    # engines:                       # omit for a single engine (outputs keep today's names)
    #   - name: whisperx
    #     url: http://localhost:9000
    #   - name: faster
    #     url: http://localhost:9001
    #     diarize: false
  ```
- Note that a named single engine still adds the `_<name>` filename segment;
  leave `engines:` unset to keep bare names.

### 8. Docs

- `CLAUDE.md` — "Processing Pipeline" and "Key Conventions": multiple ASR
  engines; one result file per engine per file/dir; index keys text by engine;
  filename segment rule.
- `docs/architecture/overview.md` — engine fan-out in the component/pipeline
  diagram.
- `docs/architecture/decisions/` — ADR: engine list vs. multiple config files;
  side table vs. wide columns; filename segment scheme.
- `docs/api/` — note that each engine entry maps to one `/asr` service.

## Files to change

- `src/whispercrawl/config.py` — `TranscriptionConfig.name` / `.engines`,
  merge + resolve in `load_config`, validation, `engine_label` helper.
- `src/whispercrawl/state.py` — schema v4, `asr_results` table + migration,
  engine args on `save_text` / `get_text` / `mark_step` / `completed_steps`,
  all-engines `done` rule, `NullState`.
- `src/whispercrawl/main.py` — per-engine transcribe/postprocess/summarize/
  finalize, per-engine directory loop, `--refresh` loop, error files.
- `src/whispercrawl/pipeline/transcriber.py` — per-engine diarize-log subdir
  (minor).
- `src/whispercrawl/pipeline/cleaner.py` / `run_cleanup` — iterate engines.
- `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`.
- `CLAUDE.md`, `docs/architecture/overview.md`,
  `docs/architecture/decisions/`, `docs/api/`.
- Tests — below.

## Acceptance Criteria

- [ ] `transcription.engines` with two entries → every file is transcribed by
  both; two result files per file (`meeting_<a>.<ext>`, `meeting_<b>.<ext>`)
  and two per directory (`_<dirname>_<a>.<ext>`, `_<dirname>_<b>.<ext>`).
- [ ] The index stores raw + post-processed text for **each** engine, keyed to
  the file's `mtime` / `size`; the engines do not overwrite each other.
- [ ] No `engines:` key → single engine, output filenames and index rows
  identical to pre-048 (no `_<engine>` segment, migrates a v3 DB in place).
- [ ] One engine returning an error writes `meeting_<engine>_err.txt` and does
  not prevent the other engine's result or the directory outputs for the
  succeeding engine.
- [ ] A file is recorded `done` only after every configured engine finished;
  removing an engine from config and re-running does not reprocess the engines
  already done.
- [ ] `--refresh` regenerates every engine's results from stored text with zero
  whisper calls; an engine with no stored text for a file is skipped (INFO, no
  `_err.txt`) while other engines still refresh.
- [ ] `--refresh` / normal run honor `processing_mode`, `skip_marker`,
  `max_age_days`, `max_files_per_run` unchanged (caps count **files**, not
  file×engine).
- [ ] `whispercrawl --cleanup` removes every configured engine's result / error
  / directory files.
- [ ] Engine `name` with a path-unsafe character, a duplicate `name`, or an
  empty `name` alongside an `engines:` list → `load_config` raises `ValueError`.
- [ ] All existing `config`, `state`, `main`, `transcriber`, `cleaner` tests
  pass or are updated for the engine dimension.

## Tests

- `tests/test_config.py`: no `engines:` → one engine, `name == ""`; `engines:`
  with two entries → merged configs inherit base `timeout` / `diarize`, entry
  overrides win; duplicate name → `ValueError`; unsafe name → `ValueError`;
  empty name + `engines:` → `ValueError`.
- `tests/test_state.py`: v3→v4 migration creates `asr_results` and copies the
  old single-column text as `engine=''`; `save_text` / `get_text` round-trip
  for two engines are independent; mismatch `mtime` → `None`; `mark_step`
  reset drops all engines' rows; per-engine step tokens; `status` reaches
  `done` only after all engines; `NullState` no-ops.
- Pipeline tests: two-engine run → two per-file and two per-dir result files
  with the expected `_<engine>` segment and content; single unnamed engine →
  byte-identical output to a pre-048 fixture; one engine error → its `_err.txt`
  only, other engine unaffected; `--refresh` per engine (mock transcriber never
  called), missing-text engine skipped; `per_step` and `per_file` produce
  identical on-disk output; `max_files_per_run` counts files.
- `tests/test_cleaner.py`: `--cleanup` with two engines removes all six files
  (2 file results + 2 dir results + errors); single-engine cleanup unchanged.
- `tests/test_transcriber.py`: per-engine diarize-log subdirectory when
  `diarize_log: true` and engine named.

## Out of Scope

- **Concurrent transcription** (calling the engines in parallel threads). This
  epic runs engines sequentially; a parallel executor is a later optimization.
  *Delivered by [[EPIC-056]] — `transcription.concurrency`, opt-in, default
  sequential.*
- **Cross-engine merged / "best of" transcript.** Each engine's output stays
  separate; picking or diffing them is a downstream tool, not this epic.
- **Per-engine `postprocessing` / `*_summarization` prompts or models.**
  Downstream steps use the single existing config for every engine. Per-engine
  downstream overrides can follow if needed.
- **Structured (segment-level) ASR storage per engine** — same limitation as
  [[EPIC-046]]; stored text is the diarized transcript at that engine's
  settings.
- **A combined per-directory result across engines.** One dir file per engine.
