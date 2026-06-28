# Backlog

Tasks are grouped by epic. Move to [done.md](done.md) when completed.

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

## EPIC-026: Formatter Speaker Style for HTML and MD

- [x] `config.py`: add `speaker_style: str = "bold"` and `text_placement: str = "same_line"` to `FormatterConfig`; validate both in `load_config` (raise `ValueError` on unknown values)
- [x] `pipeline/formatter.py`: add `_render_diarized(text) -> str` that parses `[SPEAKER_XX]: ...` lines and reformats per `speaker_style` / `text_placement`; apply in `md` and `html` branches; pass non-matching lines through unchanged
- [x] `pipeline/formatter.py` HTML: replace `<pre>` block with `<p>` tags; apply `<strong>`/`<em>` to speaker label; `new_line` inserts `<br>` between label and text
- [x] `config.yaml`, `deploy/prod/config.yaml`, `deploy/prod-local/config.yaml`: add commented `speaker_style:` and `text_placement:` under `formatter:`
- [x] Tests: MD bold same_line; MD italic new_line; MD plain same_line; HTML bold same_line; HTML em new_line; no speaker labels → content unchanged; `txt` format → style fields ignored

<!-- all tasks complete — see done.md -->
