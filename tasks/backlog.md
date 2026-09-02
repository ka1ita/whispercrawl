# Backlog

Tasks are grouped by epic. Move to [done.md](done.md) when completed.

---

## EPIC-055: A Step's Unexpected Exception Must Not Crash the Run

_Robustness fix. A `FileNotFoundError` (source moved/deleted between discovery and
transcription) and any other non-typed exception in a step currently abort the
whole run with a raw traceback; they should be recorded as an `errors` row
(as EPIC-049) and the run should continue. See [epics/EPIC-055-resilient-step-failures.md](../epics/EPIC-055-resilient-step-failures.md)._

- [x] `pipeline/transcriber.py`: wrap `open(file_path, "rb")` → `TranscriptionError("cannot read source file: ...")`; broaden request `except httpx.RequestError` to `httpx.HTTPError` (EPIC-055, 2026-09-02)
- [x] `main.py` `_transcribe_engine`: trailing `except Exception` after the `TranscriptionError` branch — `logger.exception`, `_report_error(rel, "transcribe", name, repr(e), ...)`, `file_engine_ok[...][name] = False`, `return None`; `except (KeyboardInterrupt, SystemExit)` stays first (EPIC-055, 2026-09-02)
- [x] `main.py` `_postprocess_one` / `_summarize_one`: same catch-all after the domain-exception branch — record error (`repr(e)`), `ctx["success"] = False`, return; KeyboardInterrupt/SystemExit → `partial` + re-raise (EPIC-055, 2026-09-02)
- [x] `main.py` `_finalize_one`: wrap `compose` + `result_path.write_text` in `try/except Exception` → `_report_error(rel, "finalize", eng, ...)`, mark engine failed, no partial path appended to `all_outputs_to_format` (EPIC-055, 2026-09-02)
- [x] `main.py` per-directory loop: `except SummarizationError` kept; added `except (KeyboardInterrupt, SystemExit): raise` + `except Exception` → `_report_error(dir_rel, "dir_finalize", eng, repr(e), scope="dir")` (EPIC-055, 2026-09-02)
- [x] `main.py` final formatting pass: each `formatter.format_file(path)` wrapped → `logger.exception` + `errors` row (`step="format"`); remaining outputs still formatted (EPIC-055, 2026-09-02)
- [x] `main.py` top-level file loops (both `per_file` and `per_step`): body wrapped via `_unexpected_file_failure` — `logger.exception`, best-effort `_record(rel, fst, "error", ...)`, `continue` (EPIC-055, 2026-09-02)
- [x] `file_walker.py`: `iter_media_files` skips (DEBUG) a candidate whose `stat()` raises `OSError` (vanished between scan and stat) instead of letting it escape (EPIC-055, 2026-09-02)
- [x] `state.py`: documented the new `errors.step` tokens (`finalize`, `format`, `dir_finalize`) in the schema comment (EPIC-055, 2026-09-02)
- [x] Docs: `CLAUDE.md` (pipeline description + Key Conventions), `docs/architecture/overview.md` (output conventions), new `docs/architecture/decisions/ADR-009-resilient-step-failures.md` (EPIC-055, 2026-09-02)
- [x] Tests — `test_transcriber.py`: non-existent path → `TranscriptionError("cannot read source file")`; `httpx.ConnectError` → `TranscriptionError` (EPIC-055, 2026-09-02)
- [x] Tests — new `test_resilient_failures.py`: bare `FileNotFoundError` from one file's `open()` → `errors` row + `status='error'`, second file still produces its result, run does not raise; `RuntimeError` from transcribe likewise; `Path.write_text` → `OSError` for one file → `finalize` row, no result file, other file unaffected; `Formatter.format_file` raising for one path → `format` row, others formatted; `concat_transcriptions` `RuntimeError` in one dir → `dir_finalize` `scope='dir'` row, other dir's result written; `KeyboardInterrupt` → `raises KeyboardInterrupt` + `status='partial'` (EPIC-055, 2026-09-02)
- [x] Tests — `test_file_walker.py`: candidate whose `stat` raises `FileNotFoundError` is skipped, no exception, other candidates yielded (EPIC-055, 2026-09-02)
- [x] Verified: full suite 460 passing; `ruff check src` unchanged at baseline (EPIC-055, 2026-09-02)

---

## EPIC-054: Dev Stack — Second ASR Service on :9001 and a Dedicated `deploy/dev/config.yaml`

_Depends on EPIC-048 (landed). Deployment artifacts + a dev config template only — no `src/` or test changes. See [epics/EPIC-054-dev-second-asr-engine.md](../epics/EPIC-054-dev-second-asr-engine.md). Landed 2026-09-02._

- [x] `deploy/dev/docker-compose.dev.yml`: added `whisper2` service (`9001:9000`, `${ASR_IMAGE}`, `ASR_MODEL2`/`ASR_ENGINE2` env defaulting to `tiny`/`faster_whisper`, own `whisper2_cache`, shared `hf_cache`); `whisper` gains `ASR_MODEL`/`ASR_ENGINE` env (previous hard-codes as defaults); `whisper2_cache` volume (EPIC-054, 2026-09-02)
- [x] `deploy/dev/docker-compose.dev.yml` `whispercrawl` service: mounts `./config.yaml` (`deploy/dev/config.yaml`) at `/config.yaml`; `WHISPER2_URL: http://whisper2:9000`; `depends_on` gains `whisper2` (EPIC-054, 2026-09-02)
- [x] `deploy/dev/docker-compose.services.yml`: same `whisper2` service + `whisper2_cache` volume + `ASR_MODEL`/`ASR_ENGINE` env on `whisper`; header comment updated for 127.0.0.1:9000/9001 (EPIC-054, 2026-09-02)
- [x] `deploy/dev/config.yaml` (new): dev copy of root `config.yaml` with `transcription.engines` → `whisperx` (`${WHISPER_URL:http://127.0.0.1:9000}`) + `faster` (`${WHISPER2_URL:http://127.0.0.1:9001}`, `diarize: false`); shared settings on the base block; committed to git (EPIC-054, 2026-09-02)
- [x] `deploy/dev/app-python.sh` / `app-python-once.sh` / `app-python-cleanup.sh`: `--config deploy/dev/config.yaml`; usage comments updated (EPIC-054, 2026-09-02)
- [x] `deploy/dev/services-docker-start.sh` / `services-docker-restart.sh` / `services-docker-stop.sh` / `app-docker-start.sh`: echo lines mention `whisper2 :9001` (EPIC-054, 2026-09-02)
- [x] `deploy/dev/.env.example`: commented `ASR_MODEL`/`ASR_ENGINE`/`ASR_MODEL2`/`ASR_ENGINE2` defaults with explanation (EPIC-054, 2026-09-02)
- [x] Docs — `CLAUDE.md` (Commands + config-example note), `docs/architecture/overview.md` (dev `whisper2`), new `ADR-008-dev-second-asr-engine.md`, `README.md` (dev quickstart + directory layout + mount table), `docs/api/whisper-asr-webservice.md` (EPIC-054, 2026-09-02)
- [x] Verified: `docker compose … config` clean on both dev compose files (with/without `.env`) — resolves `whisper` :9000 + `whisper2` :9001, `WHISPER2_URL=http://whisper2:9000`, mount `deploy/dev/config.yaml`; `whispercrawl --config deploy/dev/config.yaml --once --dry-run` + `load_config` resolve two engines (`whisperx` 9000 diarize=True, `faster` 9001 diarize=False); `bash -n` clean on all 7 edited scripts; root `config.yaml` unchanged (EPIC-054, 2026-09-02)

---

## EPIC-053: Remove the `cleanup:` Config Section — Drop `CleanupConfig` / `cleanup.on`

_Depends on EPIC-052. See [epics/EPIC-053-remove-cleanup-config-section.md](../epics/EPIC-053-remove-cleanup-config-section.md). Landed 2026-09-02._

- [x] `config.py`: removed `CleanupConfig` and `Config.cleanup`; dropped the `cleanup=_build(...)` line in `load_config`; a `cleanup:` key of any shape now logs one deprecation WARNING (EPIC-053, 2026-09-02)
- [x] `pipeline/cleaner.py`: `Cleaner.__init__` drops the `config` param; `clean()` gates inline on `success` (no `on == "always"` path); `CleanupConfig` import removed (EPIC-053, 2026-09-02)
- [x] `main.py` `_run_pipeline()`: `Cleaner(fmt, engine_labels=...)` — no `config.cleanup` argument; `run_cleanup()` unchanged (EPIC-053, 2026-09-02)
- [x] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: `cleanup:` block deleted, replaced with a descriptive comment only (EPIC-053, 2026-09-02)
- [x] Docs: `CLAUDE.md` `--cleanup` sentence, `docs/architecture/overview.md` (`CleanupConfig` row + `--cleanup` prose), `README.md` config table, new `ADR-007-cleanup-not-configurable.md`, `deploy/*/DEPLOY.md` cleanup sections — no `cleanup:` config / `cleanup.on` mention (EPIC-053, 2026-09-02)
- [x] Tests: `test_config.py` (no `Config().cleanup`; stale `cleanup:` → deprecation WARNING), `test_cleaner.py` rewritten to the new signature, `test_pipeline_err_cleanup.py` gains `--once --cleanup` cases, bulk-removed every `CleanupConfig` / `cleanup=` / `config.cleanup` hit; full suite green (451) (EPIC-053, 2026-09-02)

---

## EPIC-052: Cleanup Removes Only the Current Version's Outputs — Drop `error_suffix` and Legacy `cleanup.targets`

_Depends on EPIC-051. See [epics/EPIC-052-cleanup-current-outputs-only.md](../epics/EPIC-052-cleanup-current-outputs-only.md). Landed 2026-09-02._

- [x] `config.py`: remove `error_suffix` from `TranscriptionConfig` and `OllamaStepConfig`; remove `targets` from `CleanupConfig` (keep `on`); `cleanup.targets` + four `*.error_suffix` added to the deprecated-key WARNING loop (EPIC-052, 2026-09-02)
- [x] `pipeline/cleaner.py`: `clean()` removes only the single consolidated result per engine label; `clean_other_formats()` lost the `suffix_labels` param; `.json` branch gone (EPIC-052, 2026-09-02)
- [x] `main.py` `run_cleanup()`: rewritten — removes `<file>.<ext>` / `_<dirname>.<ext>` per engine in every extension, empties the index; `targets` loops, `.json` branch, and `*_err.txt` sweep all gone (EPIC-052, 2026-09-02)
- [x] `main.py` `_run_pipeline()`: `_rescan_labels` dropped; `cleaner.clean_other_formats(...)` calls updated; no `config.*.error_suffix` reference remains (EPIC-052, 2026-09-02)
- [x] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: four `error_suffix:` lines removed; `cleanup:` block is `on:` only with the "sidecars left alone" comment (EPIC-052, 2026-09-02)
- [x] Docs — `CLAUDE.md`, `docs/architecture/overview.md` (`CleanupConfig` / `StateConfig` rows, cleanup prose), `ADR-006-index-always-on.md`, `deploy/prod/DEPLOY.md`, `deploy/prod-local/DEPLOY.md` (EPIC-052, 2026-09-02)
- [x] Tests: `test_config.py` (deprecation WARNING, no `targets`/`error_suffix` attrs), `test_cleanup_cli.py` (rewritten — multi-engine + all-extension removal, `_fix`/`_err.txt` left in place), `test_pipeline/test_cleaner.py` + `test_rescan_cleans_formats.py` + `test_output_format.py` rewritten; `error_suffix=` / `targets=` kwargs dropped across the suite; 450 pass (EPIC-052, 2026-09-02)

---

## EPIC-051: The Processing Index Is Always On — Remove `state.enabled` / `state.store_text`

_See [epics/EPIC-051-always-on-processing-index.md](../epics/EPIC-051-always-on-processing-index.md). Landed 2026-09-02._

- [x] `config.py`: `StateConfig` keeps only `path`; `state.enabled` / `state.store_text` added to the deprecated-key WARNING loop (EPIC-051, 2026-09-02)
- [x] `state.py`: `open_state(path, config_root, watch_dir=None)` — `enabled` param gone, always returns `ProcessingState`; `NullState` docstring updated (`--dry-run` stand-in) (EPIC-051, 2026-09-02)
- [x] `main.py` `run_errors()`: `state.enabled: false` early-return removed; always opens the index (EPIC-051, 2026-09-02)
- [x] `main.py` `run_cleanup()` / `run_pipeline()`: `state.enabled` guard and `--refresh` precondition removed; `open_state(config.state.path, config.watch_dir, watch_dir=…)` (EPIC-051, 2026-09-02)
- [x] `main.py` `_run_pipeline()`: `_index_errors` dropped; `_report_error` always calls `state.record_error`; `_write_error()` deleted; both `store_text` guards removed; `--refresh` `--help` text trimmed (EPIC-051, 2026-09-02)
- [x] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: `state:` block is a commented `path:` hint (EPIC-051, 2026-09-02)
- [x] Docs — `CLAUDE.md` Key Conventions, `docs/architecture/overview.md`, `ADR-005` superseded note, `deploy/prod/DEPLOY.md`, `deploy/prod-local/DEPLOY.md` (EPIC-051, 2026-09-02)
- [x] Tests: `test_config.py`, `test_state.py` (new `open_state` signature), `test_refresh.py` / `test_errors_cli.py` / `test_processing_index.py` / `test_pipeline_err_cleanup.py` disabled-state cases removed; 450 pass (EPIC-051, 2026-09-02)

---

## EPIC-050: Pull the ASR Service Image from the Internal Registry (`asr-webservice:latest`)

_Deployment artifacts only — no `src/` or test changes. Landed 2026-09-02._

- [x] All three compose files (`deploy/dev/docker-compose.services.yml`, `deploy/dev/docker-compose.dev.yml`, `deploy/prod-local/docker-compose.prod-local.yml`): `whisper` service `image: ${ASR_IMAGE:-asr-webservice:latest}` (EPIC-050, 2026-09-02)
- [x] `deploy/dev/build-prod.sh`: `ASR_SRC_IMAGE` (pulled, default `onerahmet/openai-whisper-asr-webservice:latest`) + `ASR_IMAGE` (`asr-webservice:latest`); `docker tag` after pull; `docker save $ASR_IMAGE` → `whisper.tar`; `LOCAL_IMAGES` + echo text updated (EPIC-050, 2026-09-02)
- [x] `deploy/dev/.env.example`, `deploy/prod-local/.env.example`: commented `ASR_IMAGE=` entry (default + registry-override note); `deploy/prod/.env.example` untouched (EPIC-050, 2026-09-02)
- [x] `deploy/prod-local/setup.sh`: comment that `whisper.tar` loads as `asr-webservice:latest` and `ASR_IMAGE` registry path makes the load optional (EPIC-050, 2026-09-02)
- [x] Docs — `deploy/prod-local/DEPLOY.md` (image table + `ASR_IMAGE` note), `docs/api/whisper-asr-webservice.md` (snippet + "mirrored from" comment), `CLAUDE.md` (Target Environments note); `docs/architecture/overview.md` already labels the box `asr-webservice` — no `onerahmet` ref (EPIC-050, 2026-09-02)
- [x] `epics/EPIC-021-prod-local-all-in-one.md`: one-line italic note that the image was renamed in EPIC-050 (body left as historical record) (EPIC-050, 2026-09-02)
- [x] Verified: `grep -rn onerahmet` returns only README attribution + `ASR_SRC_IMAGE` default + "mirrored from" comments + EPIC-021 body; `docker compose config` resolves `asr-webservice:latest` (and the `ASR_IMAGE` override); `bash -n` clean on both scripts (EPIC-050, 2026-09-02)

---

## EPIC-049: Record Pipeline Errors in the Index, Not in `_err.txt` Sidecars

_Depends on EPIC-040 (index), EPIC-046/047/048 (index text + per-engine keys). Landed 2026-09-02._

- [x] `state.py`: `SCHEMA_VERSION` → `"5"`; `errors(path, engine, scope, step, message, mtime, size, updated_at)` table in `_SCHEMA` (create-only migration) (EPIC-049, 2026-09-02)
- [x] `state.py`: `ErrorRecord` dataclass; `record_error` / `clear_errors(engine=None)` / `get_errors(rel_path=None)` on `ProcessingState`; `mark_step` mtime/size reset also `DELETE FROM errors`; `forget` / `clear` clear it; `NullState` no-ops + `[]` (EPIC-049, 2026-09-02)
- [x] `main.py`: `_report_error(...)` helper — index row when `ProcessingState`, else `_err.txt` fallback; replace all four `_write_error(...)` call sites (EPIC-049, 2026-09-02)
- [x] `main.py`: clear errors on success — per-engine in `_finalize_one`, per-engine per-dir in the directory loop; the stale-`_err.txt` `unlink()` blocks now run only under the disabled-index fallback (EPIC-049, 2026-09-02)
- [x] `main.py`: per-directory `SummarizationError` → `record_error(dir_rel, "dir_summarize", …, scope="dir")`; no `_<dirname>_err.txt` write (EPIC-049, 2026-09-02)
- [x] `main.py`: end-of-run WARNING when `state.get_errors()` non-empty, pointing at `--errors` (EPIC-049, 2026-09-02)
- [x] `main.py`: `run_errors` + `--errors` argparse flag + branch (`--cleanup` → `--errors` → `--refresh` → `--once`/`--dry-run` → scheduler); grouped listing (UTF-8-safe print), non-zero exit when any error rows, note + exit zero when `state.enabled: false` or no index (EPIC-049, 2026-09-02)
- [x] `run_cleanup`: `*<error_suffix>.txt` sweep kept as legacy-only (comment); `state.clear()` empties `errors` (EPIC-049, 2026-09-02)
- [x] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: `error_suffix` comment (only when `state.enabled: false`); `state:` block notes `--errors` (EPIC-049, 2026-09-02)
- [x] Docs — `CLAUDE.md` (pipeline + Key Conventions), `docs/architecture/overview.md` (Error Handling Strategy + `state.py` + CLI flags), `ADR-005-errors-in-index.md`, `deploy/*/DEPLOY.md` (check-for-failures + upgrade note) (EPIC-049, 2026-09-02)
- [x] Tests — `tests/test_state.py` `TestErrorRecording`: v4→v5 create; `record_error`/`get_errors` round-trip (file + dir); upsert; `clear_errors` all vs one engine + scope-specific; `mark_step` reset drops rows; `forget`/`clear`; `NullState` (EPIC-049, 2026-09-02)
- [x] Tests — `tests/test_pipeline_err_cleanup.py` rewritten: each step failure → no `_err.txt`, one `errors` row, `status='error'`; dir failure → `scope='dir'` row; fix + rerun clears it; `state.enabled: false` → `_err.txt` fallback. `test_multi_engine` / `test_processing_index` / `test_processing_mode` / `test_postprocessor` updated for index rows (EPIC-049, 2026-09-02)
- [x] Tests — `tests/test_cleanup_cli.py`: `--cleanup` removes a legacy `*_err.txt` and empties `errors`; new `tests/test_errors_cli.py` for `--errors` (listing + exit codes + disabled/no-index note + multiline message) (EPIC-049, 2026-09-02)

---

## EPIC-048: Multiple ASR Engines — Parallel Transcription, Per-Engine Results

_Depends on EPIC-046 (landed) and EPIC-047 (landed)._

- [x] `config.py`: `TranscriptionConfig.name` / `.engines`; `load_config` merges each `engines:` entry onto the top-level `transcription:` block and resolves `config.transcription.engines` to a non-empty list (no `engines:` → `[block name=""]`) (EPIC-048, 2026-09-01)
- [x] `config.py`: validation — engine `name` matches `^[A-Za-z0-9._-]+$`, unique, non-empty when `engines:` is given → else `ValueError`; `engine_label(name)` helper (EPIC-048, 2026-09-01)
- [x] `state.py`: `SCHEMA_VERSION` → `"4"`; single `asr_results(path, engine, kind, text, mtime, size)` table holds every engine's text (`engine=""` included); `files.asr_text`/`fixed_text` columns + `Record` fields + `_TEXT_COLUMNS` dropped (EPIC-046 store had not shipped — no data migration) (EPIC-048, 2026-09-01)
- [x] `state.py`: `save_text` / `get_text` / `mark_step` / `completed_steps` gain `engine=""` (one code path, no branch); named-engine step tokens `step:<engine>`; mtime/size-mismatch reset `DELETE FROM asr_results WHERE path=?`; `forget` / `clear` clear it too; `NullState` signatures updated (EPIC-048, 2026-09-01)
- [x] `config.py`: `Config.__post_init__` fills `transcription.engines` with a copy of the base block when empty — single accessor for the engine set; `main.py` / `run_cleanup` drop the `engines or [transcription]` fallback (EPIC-048, 2026-09-01)
- [x] `main.py`: `_finalize_file` records `files.status` `done` only when every engine's context succeeded, else `error` with the failed engine names in `detail` (EPIC-048, 2026-09-01)
- [x] `main.py`: one `Transcriber` per engine (per-engine `diarize/<name>/` dir); `_transcribe_file` → list of per-engine contexts (`engine`, `elabel`, …); stored-ASR reuse and `save_text` keyed by engine (EPIC-048, 2026-09-01)
- [x] `main.py`: `engine` threaded through `_postprocess_one` / `_summarize_one` / `_finalize_one` — `output_path` / `save_text` / `mark_step` / error file all use `elabel + suffix`; `<stem>_<engine>_err.txt`; one engine failing does not block the others (EPIC-048, 2026-09-01)
- [x] `main.py`: `per_file` = file → engine → all steps; `per_step` = step → all `(file, engine)` pairs; `_finalize_file` runs once per file after the last engine (EPIC-048, 2026-09-01)
- [x] `main.py` per-directory: `dir_file_texts[dir][engine][filename]`; per engine build concat + optional summary + composed result → `{prefix}<dirname><elabel>.<ext>`; dir error `<dirname>_<engine>_err.txt` (EPIC-048, 2026-09-01)
- [x] `main.py` `--refresh`: loops engines; `state.get_text(rel, "asr", …, engine)` `None` → INFO skip that engine (others refresh); a file with no engine text leaves the index untouched, no `_err.txt`; `mark_step` per engine on success (EPIC-048, 2026-09-01)
- [x] `pipeline/transcriber.py`: no change — the per-engine `diarize_dir` is passed from `main.py` (`<log_dir>/diarize/<name>/`) (EPIC-048, 2026-09-01)
- [x] `pipeline/cleaner.py` / `run_cleanup` / `iter_media_files`: iterate `engine_labels` — `Cleaner.clean` / `clean_other_formats` and `run_cleanup` remove `<stem><label><suffix>.<ext>` + `{prefix}<dirname><label>.<ext>`; back-fill requires all engines' outputs present (EPIC-048, 2026-09-01)
- [x] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: commented `engines:` example under the flat `transcription:` base (EPIC-048, 2026-09-01)
- [x] Docs — `CLAUDE.md` Key Conventions, `docs/architecture/overview.md`, `ADR-004-multiple-asr-engines.md` (EPIC-048, 2026-09-01)
- [x] Tests — `tests/test_config.py` `TestTranscriptionEngines`: no `engines:` → one `name==""`; merge + override; duplicate / unsafe / empty-name-with-list → `ValueError` (EPIC-048, 2026-09-01)
- [x] Tests — `tests/test_state.py` `TestPerEngineText`: two engines independent; mtime mismatch → `None`; per-engine step tokens; reset drops all engines; v3 DB gains `asr_results` (EPIC-048, 2026-09-01)
- [x] Tests — `tests/test_multi_engine.py` (new, 10): two per-file + two per-dir results; per-engine index text; single unnamed engine unlabelled; engine failure isolation + retry-only-failed; `--refresh` per engine + skip missing-text engine; `per_step` == `per_file`; `--cleanup` removes every engine's outputs (EPIC-048, 2026-09-01)

---

## EPIC-047: One Consolidated Result File Per Audio File and Per Directory

_Depends on EPIC-046 (text stored in the index)._

- [x] `config.py`: `ResultConfig` already present; added `result: ResultConfig` to `Config`; `load_config` validates section names against `{"summary","transcript"}` and `heading_level` 1–6; deprecated-field WARNINGs (EPIC-047, 2026-09-01)
- [x] `pipeline/composer.py`: `compose(sections, bodies, headings, cfg)` — `# heading` + body blocks, `cfg.separator` between, single surviving section emitted bare, `include_missing_headings` honored (EPIC-047, 2026-09-01)
- [x] `pipeline/formatter.py`: `_HEADING_RE` / `_HR_RE` — `html` → `<h1..6>` / `<hr>`, `md`/`txt` passthrough; `<pre>` fallback only when neither speakers nor headings present; speaker styling still applies (EPIC-047, 2026-09-01)
- [x] `main.py` per-file: dropped `_fix` / `_sum` sidecars; `_finalize_one` composes `<file>.txt` from `{summary, transcript-body}` → deferred `formatter.format_file`; body = fixed text if postprocessing ran else raw transcript (EPIC-047, 2026-09-01)
- [x] `main.py`: `replace_transcription` branching removed from `_postprocess_one`; field still parses, `load_config` WARNs (EPIC-047, 2026-09-01)
- [x] `main.py` per-dir: one `{prefix}<dirname>.<ext>` = `compose(dir_sections, {summary, concat})`; `_all`/`_sum` sidecars gone; `run_cleanup` concat_suffix special-case removed (EPIC-047, 2026-09-01)
- [x] `main.py` per-step resume: `_summarize_one` recomputes the summary on resume (one Ollama call, cheap vs ASR); no `"summary"` index kind (EPIC-047, 2026-09-01)
- [x] `config.py` `CleanupConfig.targets` default gains `_all` / `_concat`; `clean_other_formats` is config-driven so picks them up; `run_cleanup` removes `_diarize.json` via the `.json` target (EPIC-047, 2026-09-01)
- [x] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: `result:` section (RU headings); deprecated `replace_transcription` / `output_suffix` / `concat_suffix` commented out; `cleanup.targets` gains `_concat`/`_all`; pipeline comments updated (EPIC-047, 2026-09-01)
- [x] Docs — `CLAUDE.md` (Processing Pipeline + Key Conventions), `docs/architecture/overview.md` (pipeline table + `ResultConfig`), `ADR-003-consolidated-result-file.md`, `deploy/*/DEPLOY.md` upgrade note (EPIC-047, 2026-09-01)
- [x] Tests — `tests/test_composer.py` (new, 12): section ordering / bare single section / `include_missing_headings` / custom headings / separator / level / sections filter (EPIC-047, 2026-09-01)
- [x] Tests — `tests/test_formatter.py` `TestComposedResultStructure`: `# Heading` → `<h1>` / passthrough; `---` → `<hr>`; composed doc → headings + `<p>` + styled speaker lines, never `<pre>` (EPIC-047, 2026-09-01)
- [x] Tests — pipeline: `test_output_format.py` `TestConsolidatedFileResult`; `test_pipeline/test_dir_concat.py` rewritten for the one dir result; `test_processing_mode.py` / `test_processing_index.py` / `test_postprocessor.py` / `test_refresh.py` updated; `test_cleanup_cli.py` `TestSweepsLegacySidecars` (EPIC-047, 2026-09-01)
- [x] Tests — `tests/test_config.py` `TestResultConfig`: defaults; invalid section / heading_level → `ValueError`; deprecated fields parse without error (EPIC-047, 2026-09-01)

---

## EPIC-046: Store ASR / Post-Processed Text in the Processing Index; Reprocess With `--refresh`

- [x] `state.py`: bump `SCHEMA_VERSION` to `"3"`; guarded migration adds nullable `asr_text` / `fixed_text` columns to `files` (EPIC-046, 2026-09-01)
- [x] `state.py`: `Record` gains `asr_text` / `fixed_text`; add `save_text(rel, kind, text, mtime, size)` and `get_text(rel, kind, mtime, size)` (`kind` ∈ `asr`/`fixed`; `get_text` returns `None` on mtime/size mismatch); `mark_step` reset also nulls the text columns; `NullState` no-ops (EPIC-046, 2026-09-01)
- [x] `config.py`: optional `StateConfig.store_text: bool = True` escape hatch (EPIC-046, 2026-09-01)
- [x] `main.py` `_transcribe_one`: after a successful transcribe call `state.save_text(rel, "asr", transcript, mtime, size)`; `"transcribe" in resume_steps` reads `state.get_text(rel, "asr", …)` first, then `txt_path`, then real transcribe (EPIC-046, 2026-09-01)
- [x] `main.py` `_postprocess_one`: after success call `state.save_text(rel, "fixed", fixed_text, …)`; `"postprocess" in resume_steps` reads `state.get_text(rel, "fixed", …)` before `fix_path` / `txt_path` (EPIC-046, 2026-09-01)
- [x] `file_walker.py`: add `ignore_processed: bool = False` to `iter_media_files` — yield every media file regardless of index/outputs, still applying `skip_marker` / `max_age_days` / newest-first (EPIC-046, 2026-09-01)
- [x] `main.py`: add `--refresh` argparse flag; single pass, never starts the scheduler; branch order `--cleanup` → `--refresh` → `--once`/`--dry-run` → scheduler (EPIC-046, 2026-09-01)
- [x] `main.py` refresh path: discover via ignore-processed traversal; per file `transcript = state.get_text(rel, "asr", mtime, size)` — `None` → INFO skip, no `_err.txt`; build ctx with `resume_steps = set()`; reuse `_postprocess_one` / `_summarize_one` / `_finalize_one` + dir loop unchanged; honor `processing_mode` (EPIC-046, 2026-09-01)
- [x] `main.py` refresh success: `state.mark_step` for `transcribe` + `postprocess` + `file_summarize` (plus `_finalize_one` `done`) so a later normal run skips the file (EPIC-046, 2026-09-01)
- [x] `pipeline/transcriber.py`: when `diarize_log: true` write raw JSON under `<log_dir>/diarize/<relative-path>.json`, not beside the audio (EPIC-046, 2026-09-01)
- [x] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: note in the `state:` comment that the index stores raw + fixed text for `--refresh`; document `--refresh` (requires `state.enabled: true`) (EPIC-046, 2026-09-01)
- [x] Docs — `CLAUDE.md` Key Conventions, `docs/architecture/overview.md`, `deploy/prod/DEPLOY.md`, `deploy/prod-local/DEPLOY.md`: index holds ASR/fixed text; `--refresh` re-runs downstream steps with no whisper call (EPIC-046, 2026-09-01)
- [x] Tests — `tests/test_state.py`: v2→v3 migration adds columns without touching rows; `save_text`/`get_text` round-trip; `get_text` `None` on mismatch/absent; `mark_step` reset nulls text; `NullState` no-ops (EPIC-046, 2026-09-01)
- [x] Tests — pipeline: normal run populates the text columns; `--refresh` on a `done` file does not call the transcriber and regenerates downstream outputs; `speaker_style` change + `--refresh` → new emphasis in `.md`; missing stored text → skipped, no `_err.txt`; post-`--refresh` normal run yields nothing; `per_step` vs `per_file` refresh identical; changed source between runs → refresh skips (EPIC-046, 2026-09-01)
- [x] Tests — `tests/test_file_walker.py`: `ignore_processed=True` yields every media file regardless of index/outputs, still applies `skip_marker` / `max_age_days` / newest-first (EPIC-046, 2026-09-01)
- [x] Tests — `tests/test_transcriber.py`: `_diarize.json` written under the configured log dir mirroring the relative path (EPIC-046, 2026-09-01)

<!-- all tasks complete -->

---

## EPIC-045: Formatter `speaker_style` Ignored When Speaker Timestamps Are On

- [x] `formatter.py`: broaden `_SPEAKER_RE` to `^\[(SPEAKER_[^\]]*?)\](:?)\s*(.*)$` — matches `[SPEAKER_00]:`, `[SPEAKER_00 00:00:01]`, and `[SPEAKER_00]` forms; anchored to `SPEAKER_`; captures the optional trailing colon (EPIC-045, 2026-09-01)
- [x] `formatter.py`: `_md_speaker_line` / `_html_speaker_line` take the captured colon and render the styled token as `[{label}]{colon}` — keep the colon only when the source had one (colon-form output unchanged; timestamp form → `**[SPEAKER_00 00:00:01]**`) (EPIC-045, 2026-09-01)
- [x] `formatter.py`: update `_render_md`, `_render_html` speaker branch, and the `has_speakers` check for the new capture-group indices (EPIC-045, 2026-09-01)
- [x] Tests — `tests/test_formatter.py`: timestamped label form styled (bold/italic/plain) in html + md; `text_placement: new_line` with timestamps (br / newline); `[SPEAKER_00]` no-colon form styled; colon-form assertions still pass; a `[music]`-style line not treated as a speaker line; trailing-newline + txt no-op regressions (EPIC-045, 2026-09-01)
- [x] `docs/architecture/overview.md`: note `speaker_style` covers the timestamped `[SPEAKER_XX HH:MM:SS]` label form (EPIC-045, 2026-09-01)

---

## EPIC-044: Strip the Speaker Prefix the Whisper Service Embeds in Segment Text

- [x] `transcriber.py`: add `import re`, module-level `_EMBEDDED_SPEAKER_RE` (`^\s*\[SPEAKER_\w+\]\s*:?\s*`) and `_strip_embedded_speaker` helper (loops to clear a doubled prefix) (EPIC-044, 2026-09-01)
- [x] `transcriber.py` `_format_diarized`: apply `_strip_embedded_speaker` to every segment's text in both the speaker-present and no-speaker branches; re-check emptiness after stripping; the emitted label still comes only from the `speaker` key (EPIC-044, 2026-09-01)
- [x] Tests — `tests/test_transcriber.py`: embedded tag stripped in colon + timestamp formats; `speaker` key wins over a differing embedded tag; doubled embedded tag fully removed; segment with only a tag is skipped; clean text unchanged; no-speaker branch strips a stray tag (EPIC-044, 2026-09-01)
- [x] `docs/architecture/decisions/ADR-002-strip-embedded-speaker-prefix.md` — record the service-side change and the strip decision (EPIC-044, 2026-09-01)

---

## EPIC-043: Relocate the Processing Index to a Dedicated `db/` Directory

- [x] `state.py`: `STATE_DIRNAME = "db"` (was `".whispercrawl"`); add `LEGACY_STATE_DIRNAME = ".whispercrawl"`; `default_state_path(config_root)` returns `<config_root>/db/state.db` (EPIC-043, 2026-09-01)
- [x] `state.py` `_migrate_legacy_index` + `open_state`: `open_state(enabled, path, config_root, watch_dir=None)` resolves the default from `config_root`; one-time best-effort migration — when the new path is absent but `<watch_dir>/.whispercrawl/state.db` exists, move `state.db` + `-wal`/`-shm`/`-journal` siblings to the new `db/` dir (log INFO), remove the empty legacy dir; on `OSError` log WARNING and continue with a fresh DB (EPIC-043, 2026-09-01)
- [x] `config.py` `load_config`: resolve `state.path` default to `<config-file dir>/db/state.db` via `default_state_path(Path(path).resolve().parent)` (anchored at the config file's directory, not `watch_dir`); explicit `state.path` still respected verbatim (EPIC-043, 2026-09-01)
- [x] `main.py`: `run_pipeline` passes `watch_dir=config.watch_dir` to `open_state` for the migration probe; `run_cleanup` uses the already-resolved `config.state.path` (EPIC-043, 2026-09-01)
- [x] `file_walker.py`: exclude both `STATE_DIRNAME` (`db`) and `LEGACY_STATE_DIRNAME` (`.whispercrawl`) directory names from `rglob` traversal (EPIC-043, 2026-09-01)
- [x] `Dockerfile`: add `/db` to `VOLUME` (EPIC-043, 2026-09-01)
- [x] `deploy/prod/docker-compose.prod.yml`, `deploy/prod-local/docker-compose.prod-local.yml`: add `./db:/db:Z` mount to the `whispercrawl` service; `deploy/dev/docker-compose.dev.yml`: add `../../db:/db` (EPIC-043, 2026-09-01)
- [x] `deploy/prod/setup.sh`, `deploy/prod-local/setup.sh`: `mkdir -p`/`chmod 750`/`chown` `db` alongside `audio logs`; add `db` to the non-root `sudo chown` hint (EPIC-043, 2026-09-01)
- [x] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: update the commented `state.path` hint to `./db/state.db` / `/db/state.db` with `# default: <config dir>/db/state.db` and an auto-migration note (EPIC-043, 2026-09-01)
- [x] `.gitignore`: add `/db/` and `deploy/*/db/` (keep `**/.whispercrawl/`) (EPIC-043, 2026-09-01)
- [x] Docs — `docs/architecture/overview.md`, `CLAUDE.md`, `deploy/prod/DEPLOY.md`, `deploy/prod-local/DEPLOY.md`: new default location, the `/db` mount, the one-time auto-migration, and the updated excluded-directory name (EPIC-043, 2026-09-01)
- [x] Tests — `tests/test_state.py`: `default_state_path` shape; `open_state`/`_migrate_legacy_index` migrates legacy DB (+ `-wal`/`-shm`) with records intact and removes the empty legacy dir; no move when the new path exists; fresh DB when neither exists; migration failure → WARNING + fresh DB (EPIC-043, 2026-09-01)
- [x] Tests — `tests/test_config.py`: default `state.path` resolves under the config file's directory (not `watch_dir`); explicit `state.path` respected (EPIC-043, 2026-09-01)
- [x] Tests — `tests/test_file_walker.py`: `db/` under `watch_dir` skipped by traversal; legacy `.whispercrawl/` still skipped (regression) (EPIC-043, 2026-09-01)
- [x] Tests — `tests/test_processing_index.py`: existing `--cleanup` / disabled-state / dry-run cases pass against the new `db/state.db` location (EPIC-043, 2026-09-01)

---

## EPIC-042: Configurable Processing Mode (Per-File vs Per-Step)

- [x] `config.py`: add `processing_mode: str = "per_file"` to `Config`; `load_config` validates against `("per_file", "per_step")`, raising `ValueError` otherwise (EPIC-042, 2026-09-01)
- [x] `main.py`: extract the per-file loop body into `_transcribe_one`, `_postprocess_one`, `_summarize_one`, and `_finalize_one` helpers shared by both modes (no behavior change on their own) (EPIC-042, 2026-09-01)
- [x] `main.py`: `per_file` mode calls the four helpers per file in the existing order (transcribe → postprocess → summarize → finalize), unchanged from today (EPIC-042, 2026-09-01)
- [x] `main.py`: `per_step` mode runs `_transcribe_one` across all files, then `_postprocess_one` across the survivors, then `_summarize_one` across the survivors, then `_finalize_one` across the survivors; a transcription failure excludes only that file from later steps; a postprocessing failure does not exclude a file from summarization (EPIC-042, 2026-09-01)
- [x] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: add `processing_mode: per_file` near `rescan` with a comment explaining both modes and the Ollama model-swap rationale (EPIC-042, 2026-09-01)
- [x] `docs/architecture/overview.md`, `CLAUDE.md`: document both processing modes and when to use `per_step` (EPIC-042, 2026-09-01)
- [x] Tests — `tests/test_config.py`: `processing_mode` defaults to `"per_file"`; invalid value raises `ValueError` (EPIC-042, 2026-09-01)
- [x] Tests — `tests/test_processing_mode.py` (new): `per_file` call order unchanged (regression); `per_step` call order batches by step; `per_step` transcription failure excludes only that file from later steps; `per_step` postprocessing failure still allows summarization for that file; both modes produce identical on-disk output for the same input; per-step resume (EPIC-041) works under both modes; `max_files_per_run`/`rescan` behave identically under both modes (EPIC-042, 2026-09-01)

---

## EPIC-041: Per-Step Resume in the Processing Index

- [x] `state.py`: bump `SCHEMA_VERSION` to `"2"`; migrate `files` table with `ALTER TABLE files ADD COLUMN steps TEXT NOT NULL DEFAULT ''` guarded by a `PRAGMA table_info` check (no-op on already-migrated DB) (EPIC-041, 2026-09-01)
- [x] `state.py`: `Record` gains `steps: str`; add `completed_steps(rel_path, mtime, size) -> set[str]` (empty unless stored row's mtime+size match) and `mark_step(rel_path, step, mtime, size) -> None` (resets step set on mtime/size mismatch, else unions; sets `status="partial"`) (EPIC-041, 2026-09-01)
- [x] `state.py`: `NullState` gets matching no-op `completed_steps` (always `set()`) and `mark_step` (EPIC-041, 2026-09-01)
- [x] `main.py` `_run_pipeline`: compute `resume_steps = state.completed_steps(rel, fst.st_mtime, fst.st_size)` per file when not rescanning; skip `transcriber.transcribe()` when `"transcribe"` already completed and `txt_path` exists (read transcript back from disk); skip `postprocessor.process()` when `"postprocess"` already completed (read `fixed_text` from `fix_path`, or from `txt_path` when `replace_transcription: true`); skip `file_summarizer.summarize_file()` when `"file_summarize"` already completed and `sum_path` exists (still append to `files_to_format`) (EPIC-041, 2026-09-01)
- [x] `main.py`: call `state.mark_step(rel, <step>, fst.st_mtime, fst.st_size)` immediately after each step's output is successfully written (transcribe, postprocess, file_summarize) (EPIC-041, 2026-09-01)
- [x] `file_walker.py`: fix the back-fill branch — only mark `status="done"` from output existence when `state.lookup(rel) is None` (no row at all); a file with an existing non-current row (`error`/`partial`/stale mtime) is always added to `candidates` regardless of output existence, so `main.py` can resume it (EPIC-041, 2026-09-01)
- [x] `docs/architecture/overview.md`, `CLAUDE.md`: document per-step resume and that it fixes the prior false-"done" back-fill quirk (EPIC-041, 2026-09-01)
- [x] Tests — `tests/test_state.py`: migration adds `steps` column without touching existing rows; `mark_step` accumulates across calls with unchanged mtime/size; `mark_step` resets on mtime/size mismatch; `completed_steps` empty for unknown path or mismatched mtime/size; `NullState` no-op/empty (EPIC-041, 2026-09-01)
- [x] Tests — `tests/test_file_walker.py`: file with recorded `error` row + existing `.txt` output → still yielded as candidate (regression); file with no row + existing output → still back-filled `done` and skipped (EPIC-040 behavior preserved) (EPIC-041, 2026-09-01)
- [x] Tests — pipeline integration: interrupt after transcription → rerun does not re-call transcriber, resumes postprocess+summarize, ends `done`; interrupt after postprocessing → transcriber and postprocessor not re-called, summarization resumes; source file mtime changes between attempts → all steps reprocessed from scratch (EPIC-041, 2026-09-01)

---

## EPIC-040: Persisted Processing Index and Per-Run File Cap for Large Catalogs

- [x] `state.py` (new): `ProcessingState` class over a single SQLite file (stdlib `sqlite3`, WAL); schema `files(path, mtime, size, status, updated_at, detail)` + `meta(key, value)`; `path` stored relative to `watch_dir`; `status` ∈ `done`|`error`|`partial` (EPIC-040, 2026-08-27)
- [x] `state.py`: API — `open(path)` (create+migrate, context manager), `lookup(rel)`, `is_current(rel, mtime, size)` (true only when a `done` record matches mtime **and** size), `mark(rel, status, mtime, size, detail="")`, `forget(rel)`, `clear()`; plus a `NullState` no-op variant (EPIC-040, 2026-08-27)
- [x] `config.py`: add `StateConfig(enabled: bool = True, path: Optional[str] = None)`; add `state: StateConfig` to `Config`; default `path` resolved in `load_config` to `<watch_dir>/.whispercrawl/state.db` (EPIC-040, 2026-08-27)
- [x] `config.py`: add `max_files_per_run: Optional[int] = None` to `Config` (beside `max_age_days`); `load_config` raises `ValueError` if set and `< 1` (EPIC-040, 2026-08-27)
- [x] `file_walker.py`: add `state=None` param to `iter_media_files`; when `rescan` is false and state supplied, skip files where `state.is_current(...)` with no `exists()` probes; on un-indexed files fall back to the output-existence check and `state.mark(..., "done", ...)` when outputs are found (back-fill, no reprocessing); precedence skip-marker → age → state → output-existence (EPIC-040, 2026-08-27)
- [x] `file_walker.py`: exclude `.whispercrawl/` from `rglob` traversal (EPIC-040, 2026-08-27)
- [x] `main.py` `run_pipeline()`: open state (or `NullState` when disabled) in a `with` block; pass to `iter_media_files`; apply `max_files_per_run` slice after the newest-first sort; log `N of M pending; K remain` (EPIC-040, 2026-08-27)
- [x] `main.py` `run_pipeline()`: `state.mark` `done`/`error`/`partial` per file; `del dir_file_texts[dir_path]` after each directory's summary/concat is written (EPIC-040, 2026-08-27)
- [x] `main.py` dry-run path: pass state through (read-only, never writes) (EPIC-040, 2026-08-27)
- [x] `main.py` `run_cleanup()`: call `state.clear()` after deleting outputs (non-dry-run only); dry-run logs that it would clear (EPIC-040, 2026-08-27)
- [x] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: add `state:` block and commented `max_files_per_run:` near `max_age_days` (EPIC-040, 2026-08-27)
- [x] `docs/architecture/overview.md`, `deploy/prod/DEPLOY.md`, `deploy/prod-local/DEPLOY.md`, `CLAUDE.md`: document the state store location, that deleting it is safe (re-derives from outputs, no reprocessing), and `max_files_per_run` (EPIC-040, 2026-08-27)
- [x] Tests — `tests/test_state.py` (new): open/migrate; `mark`→`lookup`; `is_current` true only on matching mtime+size; stale mtime → not current; `clear`/`forget`; context-manager close; `NullState` behavior (EPIC-040, 2026-08-27)
- [x] Tests — `tests/test_file_walker.py`: indexed `done` file → skipped with zero `exists()` calls; changed mtime → re-queued; un-indexed + existing outputs → skipped and recorded `done`; un-indexed no outputs → queued; `rescan: true` → indexed files still yielded; `state=None` → identical to pre-epic; age/skip-marker still apply first (EPIC-040, 2026-08-27)
- [x] Tests — `tests/test_config.py`: `state` defaults; `max_files_per_run` defaults `None`; `max_files_per_run: 0` → `ValueError` (EPIC-040, 2026-08-27)
- [x] Tests — pipeline/integration: `max_files_per_run=k` over N files → exactly k processed, N-k pending, second run finishes the rest; interrupted run (fail on file 3 of 5) → 1–2 `done`, 3 `error`, 4–5 pending, rerun completes without redoing 1–2; `--cleanup` empties the store; `state.enabled: false` → no `state.db`, matches EPIC-039 (EPIC-040, 2026-08-27)

---

## EPIC-039: Prioritize Newest Files and Bound Scan Age for Large Catalogs

- [x] `file_walker.py`: add `max_age_days: Optional[int] = None` parameter to `iter_media_files`; skip files whose mtime is older than the window (log DEBUG); collect surviving candidates and yield them sorted by mtime descending (newest first) instead of alphabetically
- [x] `config.py`: add `max_age_days: Optional[int] = None` to `Config`; parse from `raw.get("max_age_days")` in `load_config`
- [x] `main.py`: pass `config.max_age_days` to `iter_media_files(...)` in `run_pipeline()`
- [x] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: add commented `# max_age_days: 180` near `skip_marker`
- [x] Tests: files with different mtimes → yielded newest-first; `max_age_days` excludes older files; `max_age_days: None` → unbounded (unchanged behavior); age filter combines correctly with `rescan`, `skip_marker`, and output-existence checks

---

## EPIC-038: Setup Scripts — Install Dir, Permissions, and Docker Volume User

- [x] `deploy/prod/.env.example`, `deploy/prod-local/.env.example`: add `APP_UID`/`APP_GID` (default 1000/1000, matching `Dockerfile`'s `appuser`)
- [x] `deploy/prod/setup.sh`, `deploy/prod-local/setup.sh`: resolve `INSTALL_DIR` — positional arg or `INSTALL_DIR` env var skips prompting; otherwise prompt interactively (`read -p`) when stdin is a tty, default script location when it isn't (non-interactive/CI); `cd` into it; print it
- [x] Both `setup.sh`: copy `.env.example` → `.env` first (if absent), then source `.env` to read `APP_UID`/`APP_GID`
- [x] Both `setup.sh`: `mkdir -p audio logs` with explicit `chmod 750`
- [x] Both `setup.sh`: when running as root — create/reuse a system group/user at `APP_GID`/`APP_UID` (`whispercrawl`), `chown -R` `audio/`+`logs/` to it, `chown root:$APP_GID` + `chmod 640` `config.yaml`
- [x] Both `setup.sh`: when not running as root — skip ownership changes, print the exact `sudo` commands to run manually instead of failing
- [x] `deploy/prod/docker-compose.prod.yml`, `deploy/prod-local/docker-compose.prod-local.yml`: add `:Z` SELinux relabel suffix to the `audio`, `config.yaml`, and `logs` bind mounts for the `whispercrawl` service (no-op on non-SELinux hosts, covers RedOS 8 enforcing mode without runtime detection)
- [x] `deploy/prod/DEPLOY.md`, `deploy/prod-local/DEPLOY.md`: document `INSTALL_DIR` override, ownership/permission step, `sudo` fallback, and `:Z` SELinux behavior

---

## EPIC-037: Multiple filename_timestamp_format Values

- [x] `config.py`: widen `filename_timestamp_format` type to `Optional[Union[str, List[str]]]`
- [x] `postprocessor.py`: in `process()`, normalize a bare string into a one-item list; try each format in order with `datetime.strptime`, stopping at the first successful parse; single WARNING listing all formats tried if none match
- [x] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: document the list form in the `filename_timestamp_format` comment
- [x] Tests: list of formats, filename matches second format → shifted; filename matches first format → first one used; filename matches none → WARNING + unchanged text; existing single-string behavior unchanged (regression)

---

## EPIC-036: Absolute Speaker Timestamps from Filename

- [x] `config.py`: add `filename_timestamp_format: str | None = None` to `PostprocessingConfig`
- [x] `postprocessor.py`: add `_offset_timestamps(text, offset) -> str` — regex-find `[SPEAKER_\w+ HH:MM:SS]`, add timedelta, reformat; wrap at 24 h
- [x] `postprocessor.py`: in the main postprocess method, after all existing passes, if `filename_timestamp_format` is set, parse `Path(source).stem` with `datetime.strptime`; on failure log WARNING and skip; call `_offset_timestamps` with the resulting timedelta
- [x] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: add commented `# filename_timestamp_format: null` under `postprocessing:`
- [x] Tests: null format → no-op; valid format + matching stem → timestamps shifted; arithmetic wraps past midnight; format mismatch → WARNING + unchanged text; no speaker timestamps in text → no-op

---

## EPIC-015: Fix Diarization — Speaker Labels in Transcript

- [x] `transcriber.py`: when `diarize: true`, request `output=json`; parse segments; format as `[SPEAKER_XX]: text\n` per segment; warn (once per file) if no `speaker` field found
- [x] `transcriber.py`: when `diarize_log: true`, write JSON body from primary response instead of making a second request
- [x] `docker/docker-compose.dev.yml`: add `HF_TOKEN: ${HF_TOKEN:-}` to whisper service environment
- [x] `docker/.env.example`: add `HF_TOKEN=` entry with comment
- [x] `config/config.yaml`: add comment on `diarize` line about HF_TOKEN requirement
- [x] `README.md`: document HuggingFace token setup under dev quickstart
- [x] Tests: speaker labels present → formatted output; no speakers → plain text + WARNING; diarize=false → unchanged (output=txt)

<!-- all tasks complete — see done.md -->

---

---

## EPIC-016: Remove _err.txt After Successful Processing

- [x] Identify where full-file pipeline success is determined (orchestrator / `file_walker.py`)
- [x] After successful full-file processing, delete `<file>_err.txt` if it exists; log at DEBUG level
- [x] After successful directory summary, delete `<dirname>_err.txt` if it exists
- [x] Tests: success with pre-existing `_err.txt` → file deleted; success without `_err.txt` → no-op; step failure mid-pipeline → `_err.txt` preserved

<!-- all tasks complete — see done.md -->

---

<!-- EPIC-012 complete — see done.md -->

---

## EPIC-018: --cleanup Also Removes _err.txt Files

- [x] `main.py`: in `run_cleanup()`, collect all error suffixes from config and delete matching files recursively under `watch_dir` (EPIC-018, 2026-05-13)
- [x] Tests: `--cleanup` removes `_err.txt`; dry-run keeps it; orphan err file (no media sibling) removed; recursive subdirectory (EPIC-018, 2026-05-13)

<!-- all tasks complete — see done.md -->

---

## EPIC-017: Move config.yaml to Project Root

- [x] Move `config/config.yaml` → `config.yaml` (project root); delete `config/` directory
- [x] `docker/Dockerfile`: update `ENTRYPOINT` path to `/config.yaml`; remove `/config` from `VOLUME`
- [x] `docker/docker-compose.dev.yml`: change volume mount to `../config.yaml:/config.yaml:ro`
- [x] `docker/docker-compose.prod.yml`: change volume mount to `./config.yaml:/config.yaml:ro`
- [x] `CLAUDE.md`: update `config/config.yaml` reference to `config.yaml`
- [x] `docs/architecture/overview.md`: update `config/config.yaml` link
- [x] `docs/deploy/docker-prod.md`: remove `config/` from mkdir; update vi path and text references
- [x] `README.md`: update all `config/config.yaml` references; update mkdir commands; remove non-existent example file cp commands; update mount table

---

## EPIC-019: Deployment Packages for Prod and Dev

- [x] Create `deploy/prod/` directory with `setup.sh`, `service-start.sh`, `service-down.sh`
- [x] Add `deploy/prod/docker-compose.prod.yml` (standalone, env-var driven URLs)
- [x] Add `deploy/prod/config.yaml` — production config template with placeholder URLs, `/audio` and `/logs` paths set
- [x] Add `deploy/prod/dist/.gitkeep`
- [x] Move `docs/deploy/docker-prod.md` content to `deploy/prod/DEPLOY.md`; replace `docs/deploy/docker-prod.md` with redirect stub
- [x] Update `docker/export-image.sh` to copy built tar into `deploy/prod/dist/` after saving
- [x] Create `deploy/dev/` directory with `start.sh`, `stop.sh`, `rebuild.sh`, `start-external.sh`
- [x] All scripts: `set -euo pipefail`, resolve paths relative to script location, executable bit set via git

<!-- all tasks complete — see done.md -->

---

## EPIC-020: Rename Project to WhisperCrawl

- [x] Rename `src/fileswhisper/` → `src/whispercrawl/`; update all internal Python imports
- [x] Update all test imports from `fileswhisper` → `whispercrawl`
- [x] `pyproject.toml`: rename `name`, `packages`, and `[project.scripts]` entrypoint (`whispercrawl`)
- [x] `deploy/dev/docker-compose.dev.yml`: rename service `fileswhisper` → `whispercrawl`; update comments
- [x] `deploy/prod/docker-compose.prod.yml`: rename service and image `fileswhisper` → `whispercrawl`
- [x] `deploy/dev/build-prod.sh`: update image name and tar filename
- [x] `deploy/dev/rebuild.sh`: update service name and comment
- [x] `deploy/prod/setup.sh`: update image name and tar filename
- [x] `CLAUDE.md`, `README.md`, `deploy/prod/DEPLOY.md`: replace all `fileswhisper`/`filesWhisper` references

<!-- all tasks complete — see done.md -->

---

## EPIC-021: prod-local — All-in-One Single-Server Deployment

- [x] `deploy/prod-local/`: create directory with `dist/.gitkeep`
- [x] `deploy/prod-local/docker-compose.prod-local.yml`: all three services (whisper, ollama, whispercrawl) on internal network; service URLs hard-coded to container names
- [x] `deploy/prod-local/.env.example`: `ASR_MODEL`, `HF_TOKEN` vars with comments
- [x] `deploy/prod-local/config.yaml`: prod config template with internal service URLs (`http://whisper:9000`, `http://ollama:11434`), `/audio` and `/logs` paths set
- [x] `deploy/prod-local/setup.sh`: load all three image tars from `dist/`; create `audio/`, `logs/`; copy `.env.example` → `.env` if absent; print next steps
- [x] `deploy/prod-local/service-start.sh`: `docker compose -f docker-compose.prod-local.yml up -d`
- [x] `deploy/prod-local/service-down.sh`: `docker compose -f docker-compose.prod-local.yml down`
- [x] `deploy/prod-local/DEPLOY.md`: operator manual (prerequisites, transfer, setup, model pull, env config, start/stop)
- [x] `deploy/dev/build-prod.sh`: pull and save `whisper.tar` and `ollama.tar` alongside `whispercrawl.tar`; write all three into both `deploy/prod/dist/` and `deploy/prod-local/dist/`

<!-- all tasks complete — see done.md -->

---

## EPIC-022: Configurable Output Format (TXT / HTML)

- [x] `config.py`: add `output_format: str = "txt"` to `Config`; validate in `load_config` (raise `ValueError` on unknown value)
- [x] `config.py`: change all `output_suffix` / `error_suffix` defaults to label-only (no extension): `""`, `"_fix"`, `"_sum"`, `"_err"`; update `CleanupConfig.targets` to `["", "_fix", "_sum", "_diarize.json"]`
- [x] `main.py`: add `output_path(base, suffix, fmt) -> Path` helper; replace all ad-hoc `with_name(stem + suffix)` calls with it; apply to both file and dir output paths
- [x] `main.py`: add `render_output(text, fmt) -> str` helper (identity for `"txt"`, minimal HTML shell with escaped content for `"html"`); apply before every `write_text` call in `run_pipeline`
- [x] `file_walker.py`: pass `output_format` to `iter_media_files`; derive skip-check extension from format
- [x] `pipeline/summarizer.py`: update `summarize_directory` glob pattern to use format-derived extension
- [x] `pipeline/cleaner.py`: make `Cleaner` format-aware; derive extension from `output_format`
- [x] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: add `output_format: txt`; update all suffix fields to label-only form; update `cleanup.targets`
- [x] Tests: update existing suffix expectations; add cases — TXT path unchanged; HTML wraps + escapes; `--cleanup` removes `.html` outputs when format is html

<!-- all tasks complete — see done.md -->

---

## EPIC-023: Centralize Output Format Conversion in a Final Formatter Step

- [x] `pipeline/formatter.py`: create `Formatter` class with `format_file(txt_path) -> Path` (no-op for `"txt"`; read→wrap→write `.html`→delete `.txt` for `"html"`)
- [x] `main.py`: remove `render_output()` from every `write_text()` call in `run_pipeline()`; pipeline steps always write plain `.txt`
- [x] `main.py`: after each file's steps complete, call `formatter.format_file()` for each written output path; after each dir summary, call `formatter.format_file()` for the dir summary; error files always written as `.txt`
- [x] `pipeline/summarizer.py`: remove `output_format` parameter from `summarize_directory()`; always glob `*{suffix}.txt`
- [x] Tests: `test_formatter.py` (unit); html run → no orphan `.txt` output files; txt run → `.txt` present, no `.html`; dir summarizer reads plain `.txt` only; `replace_transcription` still works end-to-end

<!-- all tasks complete — see done.md -->

---

## EPIC-024: Formatter Config Section

- [x] `config.py`: add `FormatterConfig` dataclass (`format: str = "txt"`, `enabled: bool = True`); replace `Config.output_format` with `Config.formatter: FormatterConfig`; move format validation into `load_config` after building `FormatterConfig`
- [x] `main.py`: replace all `config.output_format` with `config.formatter.format`; when `enabled: false`, pass `"txt"` to `Formatter` (no-op) regardless of `format`
- [x] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: replace top-level `output_format:` with `formatter:` section (`format:` + commented `enabled:`)
- [x] Tests: update all `Config(output_format=...)` constructions to `Config(formatter=FormatterConfig(...))`; add test that `enabled: false` with `format: html` leaves files as `.txt`

<!-- all tasks complete — see done.md -->

---

## EPIC-025: Add Markdown Format to Formatter

- [x] `config.py`: add `"md"` to the allowed values in `load_config` format validation
- [x] `pipeline/formatter.py`: add `"md"` branch to `format_file()` — read `.txt`, write `.md`, delete `.txt`
- [x] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: update `format:` comment to `txt | html | md`
- [x] Tests: md run → `.md` produced, no orphan `.txt`; txt/html runs unaffected; `--cleanup` removes `.md` when format is `md`

<!-- all tasks complete — see done.md -->

---

## EPIC-027: Cleanup and Skip-Check Use Format Extension for MD and HTML

- [x] `main.py`: fix `output_path()` — add `elif fmt == "md": ext = ".md"` so all three formats return the correct extension
- [x] `pipeline/cleaner.py`: fix `Cleaner.__init__` — derive `self._ext` for `"md"` the same way
- [x] `file_walker.py`: fix `iter_media_files` — derive `ext` for `"md"` the same way
- [x] Tests: `run_cleanup` with `format: md` removes `.md` files; `Cleaner` removes `.md` files; `iter_media_files` skips files when `.md` output already exists; existing txt/html cases must not regress

---

## EPIC-028: Skip Files Whose Output Exists in a Different Format

- [x] `file_walker.py` — `iter_media_files`: replace single-extension skip check with a multi-extension check — when `rescan` is false, skip the file if an output file with the same stem exists in *any* supported extension (`.txt`, `.md`, `.html`)
- [x] Tests: file processed as `txt`, config changed to `md` → skipped; file processed as `md`, config changed to `html` → skipped; file processed as `html`, config changed to `txt` → skipped; `rescan: true` with cross-format output → file re-queued; no output in any format → file queued

---

## EPIC-029: rescan: true Cleans Output Files in Other Formats

- [x] `pipeline/cleaner.py`: add `clean_other_formats(file_path, suffix_labels, current_ext)` method — for each suffix label and each supported extension that is NOT current_ext, delete the file if it exists; log at INFO; skip `_err.txt` and `_diarize.json`
- [x] `main.py`: in `run_pipeline()`, at the start of each file when `config.rescan` is true, call `cleaner.clean_other_formats()` with the configured suffix labels and current format extension; in dry-run mode, log what would be deleted without deleting
- [x] Tests: `rescan: true`, orphan `.txt` when format is `md` → `.txt` outputs deleted; orphan `.md` when format is `html` → `.md` outputs deleted; orphan `.html` when format is `txt` → `.html` outputs deleted; `rescan: true`, no orphans → no-op; `rescan: false` → orphans untouched; `_err.txt` and `_diarize.json` never deleted; dry-run → logged but not deleted

---

## EPIC-026: Formatter Speaker Style for HTML and MD

- [x] `config.py`: add `speaker_style: str = "bold"` and `text_placement: str = "same_line"` to `FormatterConfig`; validate both in `load_config` (raise `ValueError` on unknown values)
- [x] `pipeline/formatter.py`: add `_render_diarized(text) -> str` that parses `[SPEAKER_XX]: ...` lines and reformats per `speaker_style` / `text_placement`; apply in `md` and `html` branches; pass non-matching lines through unchanged
- [x] `pipeline/formatter.py` HTML: replace `<pre>` block with `<p>` tags; apply `<strong>`/`<em>` to speaker label; `new_line` inserts `<br>` between label and text
- [x] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: add commented `speaker_style:` and `text_placement:` under `formatter:`
- [x] Tests: MD bold same_line; MD italic new_line; MD plain same_line; HTML bold same_line; HTML em new_line; no speaker labels → content unchanged; `txt` format → style fields ignored

<!-- all tasks complete — see done.md -->

---

## EPIC-032: Immediate First Run on Service Start

- [x] `scheduler.py`: in `start_scheduler()`, call `run_pipeline(config)` once (with a log line) immediately after registering the job and before calling `scheduler.start()`
- [x] Tests: verify `run_pipeline` is called before `scheduler.start()` for both cron and interval schedule types; verify the scheduler job is still registered for subsequent runs

---

## EPIC-031: Skip Files Containing a Configurable Marker in Their Name

- [x] `config.py`: add `skip_marker: str = "_skip"` field to `Config` dataclass
- [x] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: add commented `skip_marker: _skip` line near `rescan`
- [x] `file_walker.py`: add `skip_marker: str = ""` parameter to `iter_media_files`; skip file (log DEBUG) when `skip_marker` is non-empty and found in `path.stem` (case-insensitive); check runs before rescan/output-existence logic
- [x] `main.py`: pass `config.skip_marker` to `iter_media_files` in `run_pipeline()` and `run_dry_run()`
- [x] Tests: marker present → skipped; upper-case marker → skipped; marker mid-stem → skipped; `skip_marker: ""` → file yielded; no marker → yielded; marker check runs even when no output exists

---

## EPIC-033: Per-Directory Concatenation of Transcriptions

- [x] `config.py`: add `concat_source: str = "postprocessed"`, `underscore_prefix: bool = False`, `concat_suffix: str = "_concat"` to `DirSummarizationConfig`; validate `concat_source` in `load_config`
- [x] `pipeline/summarizer.py`: replace `summarize_directory()` with `concat_transcriptions(texts_by_name, concat_source)` (joins in-memory texts with `\n\n---\n\n`; raises `SummarizationError` if dict is empty) and `summarize_text(text, label)` (thin `_call_ollama` wrapper); keep `summarize_file` as alias or remove if unused
- [x] `main.py`: collect per-file transcription texts in a `dir_texts` dict during the file loop; after the loop, for each dir compute `dir_base` with optional `_` prefix; write concat file as plain `.txt`; if `llm_enabled`, call `summarize_text` and write summary via `output_path`; add summary to `all_outputs_to_format`
- [x] `main.py` cleanup: update `run_cleanup` dir-base derivation to apply the same `underscore_prefix` logic
- [x] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: add `concat_source: postprocessed`; add commented `underscore_prefix: false` and `concat_suffix: _concat`; update `dir_summarization` prompt to reflect full-transcription input
- [x] Tests: `concat_transcriptions` — two texts joined with separator; empty dict → `SummarizationError`; `concat_source: postprocessed` falls back to original when fix text absent
- [x] Tests: `underscore_prefix: false` → `<dirname>_sum.<ext>`; `underscore_prefix: true` → `_<dirname>_sum.<ext>` and `_<dirname>_concat.txt`; concat file always `.txt`; Formatter applied to summary only; `run_cleanup` removes both files when suffixes in targets

---

## EPIC-034: Filename Headers in Concat and Formatter Pass for Concat File

- [x] `pipeline/summarizer.py`: in `concat_transcriptions()`, prefix each block with the sorted filename key on its own line; keep `\n\n---\n\n` separator between blocks; no trailing separator
- [x] `main.py`: add `concat_path` to `all_outputs_to_format` after writing it
- [x] `main.py` `run_cleanup()`: replace the hardcoded-`.txt` concat path with `output_path(dir_base, concat_suffix, fmt)`; remove the "always plain .txt" special-case branch
- [x] Tests: `concat_transcriptions` two files → filename headers present in sorted order; separator only between blocks; existing empty-dict → `SummarizationError` unchanged
- [x] Tests: `format: md` → concat file written as `.md`; `format: html` → `.html`; `format: txt` → `.txt`; `run_cleanup` removes correct extension for each format

---

## EPIC-035: Speaker Timestamps in Diarized Transcription Output

- [x] `config.py`: add `speaker_timestamps: bool = False` to `TranscriptionConfig`
- [x] `pipeline/transcriber.py`: in `_format_diarized()`, when `speaker_timestamps` is true, read `seg.get("start")`, format as `HH:MM:SS`, emit `[SPEAKER_XX HH:MM:SS] text`; fall back gracefully if `start` is absent
- [x] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: add commented `speaker_timestamps: false` under `transcription:`
- [x] Tests: `speaker_timestamps: false` → format unchanged; `speaker_timestamps: true`, start present → timestamp included; `speaker_timestamps: true`, start missing → no exception, label without timestamp; `diarize: false` → setting ignored; timestamp wraps hours correctly

---

## EPIC-030: Run Formatter After Directory Summarization

- [x] `main.py`: remove `formatter.format_file()` calls from inside the per-file loop; accumulate all `files_to_format` paths only (no immediate conversion)
- [x] `main.py`: after the dir-summarization loop, run `formatter.format_file()` on all accumulated per-file output paths
- [x] `main.py`: collect dir summary paths and include them in the same final formatting pass
- [x] Tests: `format: md`, file + dir summarization enabled → dir summary succeeds and is written as `.md`; no `_sum.txt` orphan files remain
- [x] Tests: `format: html`, same conditions → dir summary written as `.html`
- [x] Tests: `format: txt` → all outputs remain `.txt`; dir summary succeeds as before; no regressions
