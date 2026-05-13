# Done

Completed tasks moved here from [backlog.md](backlog.md).

<!-- Format: - [x] Task description (EPIC-XXX, YYYY-MM-DD) -->

## EPIC-001: Transcription & Diarization

- [x] Implement `Config` dataclass and YAML loader (`config.py`) (EPIC-001, 2026-05-11)
- [x] Implement `FileWalker` with skip-processed and full-rescan modes (`file_walker.py`) (EPIC-001, 2026-05-11)
- [x] Implement language detection from filename suffix (`_ru`, `_en`, `_auto`) (EPIC-001, 2026-05-11)
- [x] Implement `Transcriber.transcribe(file_path) -> str` calling whisper API (`pipeline/transcriber.py`) (EPIC-001, 2026-05-11)
- [x] Implement output file writer with success/error logic (EPIC-001, 2026-05-11)
- [x] Write unit tests for `FileWalker` (mock filesystem) (EPIC-001, 2026-05-11)
- [x] Write integration test for `Transcriber` (mock HTTP) (EPIC-001, 2026-05-11)

## EPIC-002: Post-Processing

- [x] Implement `PostProcessor.process(text: str) -> str` with regex pass + ollama call (EPIC-002, 2026-05-11)
- [x] Load regex patterns from config (EPIC-002, 2026-05-11)
- [x] Write unit tests for regex cleanup (EPIC-002, 2026-05-11)
- [x] Write integration test for LLM post-processing (mock ollama) (EPIC-002, 2026-05-11)

## EPIC-003: Summarization

- [x] Implement `Summarizer.summarize_file(text: str) -> str` (EPIC-003, 2026-05-11)
- [x] Implement `Summarizer.summarize_directory(dir_path: Path) -> str` (EPIC-003, 2026-05-11)
- [x] Ensure directory summary runs after all file summaries in that directory (EPIC-003, 2026-05-11)
- [x] Write tests for both summarization modes (per-file and per-directory) (EPIC-003, 2026-05-11)

## EPIC-004: Scheduler & CLI

- [x] Implement CLI with `--config`, `--once`, `--dry-run` flags (`main.py`) (EPIC-004, 2026-05-11)
- [x] Implement `Scheduler` wrapping APScheduler cron job (`scheduler.py`) (EPIC-004, 2026-05-11)
- [x] Support both cron expressions and interval strings (`30m`, `1h`) (EPIC-004, 2026-05-11)
- [x] Handle SIGTERM / SIGINT for graceful shutdown (EPIC-004, 2026-05-11)
- [x] Write integration test for `--once --dry-run` (EPIC-004, 2026-05-11)

## EPIC-005: Output Cleanup & Service Interaction Logging

- [x] Add `CleanupConfig` dataclass to `config.py` (`enabled`, `targets`, `on`) (EPIC-005, 2026-05-11)
- [x] Implement `Cleaner` class in `pipeline/cleaner.py` (EPIC-005, 2026-05-11)
- [x] Call `Cleaner` at the end of `run_pipeline()` in `main.py` (EPIC-005, 2026-05-11)
- [x] Load cleanup section in `load_config()` (EPIC-005, 2026-05-11)
- [x] Write unit tests for `Cleaner` (file removal logic, `on: success` vs `on: always`) (EPIC-005, 2026-05-11)
- [x] Add `LoggingConfig` dataclass to `config.py` (`requests`, `log_file`) (EPIC-005, 2026-05-11)
- [x] Implement `ServiceLogger` context manager in `utils/service_logger.py` (EPIC-005, 2026-05-11)
- [x] Inject `ServiceLogger` into `Transcriber`, `PostProcessor`, and `Summarizer` (EPIC-005, 2026-05-11)
- [x] Load logging section in `load_config()` (EPIC-005, 2026-05-11)
- [x] Write unit tests for `ServiceLogger` (log line fields, ndjson file output) (EPIC-005, 2026-05-11)

## EPIC-006: --cleanup CLI Flag

- [x] Implement `run_cleanup()` in `main.py` (EPIC-006, 2026-05-11)
- [x] Add `--cleanup` argument to the CLI parser (EPIC-006, 2026-05-11)
- [x] Write unit tests for `run_cleanup` (files deleted, dry-run, no outputs present) (EPIC-006, 2026-05-11)

## EPIC-007: ASR Engine Configuration

- [x] Add `asr_engine`, `initial_prompt`, `vad_filter`, `word_timestamps`, `encode` to `TranscriptionConfig` (EPIC-007, 2026-05-11)
- [x] Forward non-None fields as query params in `Transcriber` (EPIC-007, 2026-05-11)
- [x] Update `config/config.example.yaml` with new fields and allowed values (EPIC-007, 2026-05-11)
- [x] Write unit tests for param forwarding (all set, all None, mixed, timeout, request error) (EPIC-007, 2026-05-11)

## EPIC-008: Split Postprocessing Enabled Flags

- [x] Add `regex_enabled: bool = True` to `OllamaStepConfig` (EPIC-008, 2026-05-11)
- [x] Update `PostProcessor.process()` to check `llm_enabled` and `regex_enabled` independently (EPIC-008, 2026-05-11)
- [x] Update `main.py` to instantiate `PostProcessor` when either flag is true (EPIC-008, 2026-05-11)
- [x] Update `config/config.example.yaml` with both flags (EPIC-008, 2026-05-11)
- [x] Add tests for all four flag combinations (EPIC-008, 2026-05-11)
- [x] Rename `enabled` → `llm_enabled` in `OllamaStepConfig` and update all call sites (EPIC-008, 2026-05-11)

## EPIC-009: Enhanced Service Logging

- [x] Add `log_dir` and `max_text_length` to `LoggingConfig` (EPIC-009, 2026-05-11)
- [x] Extend `ServiceLogger.log()` with `method`, `url`, `params`, `request_body`, `response_body` (EPIC-009, 2026-05-11)
- [x] Support `log_dir` path resolution with auto-created directory (EPIC-009, 2026-05-11)
- [x] Implement `_truncate` / `_truncate_nested` for `max_text_length` (EPIC-009, 2026-05-11)
- [x] Update `Transcriber`, `PostProcessor`, `Summarizer` to pass full HTTP context to logger (EPIC-009, 2026-05-11)
- [x] Update `config/config.example.yaml` with new logging fields (EPIC-009, 2026-05-11)
- [x] Write tests for log_dir, log_file precedence, watch_dir fallback, truncation (EPIC-009, 2026-05-11)

## EPIC-010: Application Log File

- [x] Add `app_log_file`, `app_log_level`, `app_log_max_bytes`, `app_log_backup_count` to `LoggingConfig` (EPIC-010, 2026-05-11)
- [x] Implement `setup_logging()` in `utils/logging_setup.py` with `StreamHandler` + optional `RotatingFileHandler` (EPIC-010, 2026-05-11)
- [x] Replace `logging.basicConfig()` in `main.py` with `setup_logging(config.logging)` (EPIC-010, 2026-05-11)
- [x] Update `config/config.example.yaml` with new fields (EPIC-010, 2026-05-11)
- [x] Write unit tests for `setup_logging` (file handler, directory creation, rotation, log levels) (EPIC-010, 2026-05-11)

## EPIC-011: Summarization Source Selection

- [x] Add `summarize_source: str = "postprocessed"` to `OllamaStepConfig` (EPIC-011, 2026-05-11)
- [x] Add `_pick_summary_input()` helper to `main.py` with fallback + warning (EPIC-011, 2026-05-11)
- [x] Update `run_pipeline()` to track `fixed_text` separately and resolve summary input (EPIC-011, 2026-05-11)
- [x] Update `config/config.example.yaml` and `config.yaml` with `summarize_source` field (EPIC-011, 2026-05-11)
- [x] Write tests for both source modes and fallback logic (EPIC-011, 2026-05-11)

## EPIC-012: Docker Environments

- [x] Write `docker/Dockerfile` (multi-stage, non-root, entry point `fileswhisper --config /config/config.yaml`) (EPIC-012, 2026-05-11)
- [x] Write `docker/docker-compose.dev2.yml` (all three services in Docker) (EPIC-012, 2026-05-11)
- [x] Write `docker/docker-compose.dev1.yml` (filesWhisper only, host services via `host.docker.internal`) (EPIC-012, 2026-05-11)
- [x] Write `docker/docker-compose.prod.yml` (filesWhisper only, `WHISPER_URL` / `OLLAMA_URL` env vars) (EPIC-012, 2026-05-11)
- [x] Add `/audio`, `/config`, `/logs` volume mounts to all compose files (EPIC-012, 2026-05-11)
- [x] Add per-environment config examples and `.env.example` (EPIC-012, 2026-05-11)
- [x] Write `docker/export-images.sh` and `docker/import-images.sh` for air-gap transfer (EPIC-012, 2026-05-11)
- [x] Add `os.path.expandvars()` to `load_config()` for `${VAR}` substitution in config (EPIC-012, 2026-05-11)
- [x] Update `README.md` with per-environment quickstart and `docker/` layout (EPIC-012, 2026-05-11)

## EPIC-013: Replace Transcription with Postprocessed Output

- [x] Add `replace_transcription: bool = False` to `OllamaStepConfig` in `config.py` (EPIC-013, 2026-05-12)
- [x] In `main.py`: after writing `_fix.txt`, if flag set rename it over `.txt` (EPIC-013, 2026-05-12)
- [x] Update `config/config.yaml` with `replace_transcription` field (EPIC-013, 2026-05-12)
- [x] Write `tests/test_postprocessor.py` covering both flag values (EPIC-013, 2026-05-12)

## EPIC-014: Diarization Response Logging

- [x] Add `diarize_log: bool = False` to `TranscriptionConfig` in `config.py` (EPIC-014, 2026-05-12)
- [x] In `transcriber.py`: after successful txt call, if `diarize_log` set make second POST with `output=json` and write `<file>_diarize.json` (errors → warning only) (EPIC-014, 2026-05-12)
- [x] When `diarize: false`, skip the second request regardless of `diarize_log` (EPIC-014, 2026-05-12)
- [x] Add `_diarize.json` to default cleanup targets (EPIC-014, 2026-05-12)
- [x] Update `config/config.yaml` with `diarize_log` field and comment (EPIC-014, 2026-05-12)
- [x] Write `tests/test_transcriber.py`: 7 cases covering all flag/failure combinations (EPIC-014, 2026-05-12)

## Infrastructure

- [x] Set up `pyproject.toml` with all dependencies (2026-05-11)
- [x] Configure `ruff` for linting and formatting (2026-05-11)
- [x] Configure `pytest` with coverage (2026-05-11)
- [x] Finalize `docker-compose.dev.yml` (whisper + ollama) (2026-05-11)
- [x] Write `README.md` with quickstart instructions (2026-05-11)
- [x] Update `CLAUDE.md` with epic/task workflow guidance for Claude (2026-05-11)
