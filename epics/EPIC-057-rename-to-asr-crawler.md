# EPIC-057: Rename Project to asr-crawler

**Status**: Landed 2026-09-03.

## Goal

Rename the project from `whispercrawl` / `WhisperCrawl` to `asr-crawler` across
every artefact — Python package, CLI entrypoint, Docker image, compose services,
deploy scripts, config comments, tests, and documentation — so the new name is
reflected consistently everywhere.

## Background

`whispercrawl` bakes one ASR backend (Whisper) into the product name. Since
[[EPIC-048]] the service drives an arbitrary list of ASR engines
(`whisperx`, `gigaam`, …), and the mirrored service image was already renamed
`whisper-asr-webservice` → `asr-webservice` in [[EPIC-050]]. `asr-crawler` matches
that: it crawls directories and runs whatever ASR engines are configured.

This is a pure rename — no behaviour, config schema, pipeline, or output changes.
It mirrors [[EPIC-020]] (`filesWhisper` → `whispercrawl`).

## Naming decisions

| Thing | Old | New |
| --- | --- | --- |
| Distribution / project name (`pyproject.toml`) | `whispercrawl` | `asr-crawler` |
| CLI command | `whispercrawl` | `asr-crawler` |
| Import package (dir under `src/`) | `whispercrawl` | `asr_crawler` (underscore — hyphens are illegal in module names) |
| Docker image | `whispercrawl` | `asr-crawler` |
| Compose service | `whispercrawl` | `asr-crawler` |
| App log file | `whispercrawl.log` | `asr-crawler.log` |

Left **unchanged** (historical on-disk artefacts, not the product name):

- `LEGACY_STATE_DIRNAME = ".whispercrawl"` in `state.py` and the matching
  `**/.whispercrawl/` line in `.gitignore` — these name directories that *old
  installations already created on disk*; the pre-[[EPIC-043]] migration must
  keep finding them. Update only the surrounding comments/docstrings that use
  "whispercrawl" as the product name.

Out of scope (operator actions, not code changes):

- The working directory / git repo / GitHub remote name (`c:\_Project\whispercrawl`).
- Retroactive edits to existing `epics/*` and `docs/architecture/decisions/ADR-*`
  files — they are a historical record; new work uses the new name. (`CLAUDE.md`,
  `README.md`, `docs/architecture/overview.md`, `docs/api/*`, and `docs/*/DEPLOY.md`
  ARE updated — they describe the current system.)

---

## Scope

### Python package

- `git mv src/whispercrawl src/asr_crawler` (preserve history).
- Rewrite every `from whispercrawl.` / `import whispercrawl` →
  `asr_crawler` in `src/` and `tests/`.
- Internal module docstrings / log strings / comments that say "whispercrawl" or
  "WhisperCrawl" as the product → "asr-crawler".
- `pyproject.toml`: `[project].name` → `asr-crawler`; `[project.scripts]` →
  `asr-crawler = "asr_crawler.main:main"`; `[tool.hatch.build.targets.wheel].packages`
  → `["src/asr_crawler"]`.
- `src/asr_crawler/__main__.py` import.
- Regenerate `uv.lock` (or hand-edit the single `name = "whispercrawl"` entry).

### CLI / help text

- `argparse` `prog=` / usage / epilog strings in `main.py` that print
  `whispercrawl`.
- Any `--errors` / `--cleanup` / `--refresh` help text mentioning the command name.

### Docker

- `Dockerfile`: `COPY --from=builder /usr/local/bin/whispercrawl …` and the
  `ENTRYPOINT` → `asr-crawler`.
- `deploy/dev/docker-compose.dev.yml`, `deploy/dev/docker-compose.services.yml`,
  `deploy/prod/docker-compose.prod.yml`,
  `deploy/prod-local/docker-compose.prod-local.yml`: service name
  `whispercrawl` → `asr-crawler`, plus `container_name`, `image:`, and any
  `depends_on` / volume-label references.
- `deploy/dev/docker-rebuild-app.sh`, `deploy/dev/docker-export-prod.sh`,
  `deploy/dev/services-docker-*.sh`, `deploy/dev/app-docker-start.sh`,
  `deploy/prod/setup.sh`, `deploy/prod/service-cleanup.sh`,
  `deploy/prod-local/setup.sh`: image / service / `docker compose … <service>`
  references, and any `docker save`/`docker load` hard-coded image names.

### Deploy scripts & env

- `deploy/dev/app-python*.sh` (`app-python.sh`, `app-python-once.sh`,
  `app-python-cleanup.sh`): the `python -m whispercrawl` / `whispercrawl …`
  invocation.
- `deploy/*/.env.example`, `deploy/prod-local/.env.example`: any
  `whispercrawl`-named vars or defaults (e.g. `LOGS_DIR` comments,
  `app_log_file` default).

### Config files

- `config.yaml`, `deploy/dev/config.yaml`, `deploy/prod/config.yaml`,
  `deploy/prod-local/config.yaml`: header comment (`# WhisperCrawl configuration`),
  the `whispercrawl --refresh` / `--errors` / `--cleanup` usage comments, and
  `logging.app_log_file` default (`…/whispercrawl.log` → `…/asr-crawler.log`).
- Config schema keys and values are **unchanged**.

### `.claude/settings.json`

- The permission entry embedding
  `from whispercrawl.config import load_config` → `asr_crawler`.

### Tests

- Rewrite imports across `tests/` (`whispercrawl` → `asr_crawler`).
- Update any test that asserts on the CLI `prog` name, the log filename,
  compose service name, or image name.
- `tests/` fixtures / expected strings containing "whispercrawl".

### Documentation

- `CLAUDE.md`: every `whispercrawl` command, path (`src/whispercrawl/…`),
  image / service name, and the project-overview prose.
- `README.md`: install/run commands, package name, Docker references.
- `docs/architecture/overview.md`: component name.
- `docs/api/whisper-asr-webservice.md` and any other `docs/` mention of the
  product name (the ASR *service* doc name stays — it is about the upstream
  service).

---

## Acceptance Criteria

- [ ] `src/asr_crawler/` exists (moved with history); `src/whispercrawl/` is gone.
- [ ] `grep -rn 'whispercrawl\|WhisperCrawl' src tests` is empty **except**
  `LEGACY_STATE_DIRNAME` and its docstring reference in `state.py`.
- [ ] `pip install -e ".[dev]"` succeeds; `asr-crawler --help` works;
  `whispercrawl` is no longer a command.
- [ ] `pytest` passes with no import errors.
- [ ] `ruff check src tests` and `ruff format --check src tests` are clean.
- [ ] `docker compose -f deploy/dev/docker-compose.dev.yml --env-file deploy/dev/.env config`
  resolves; the app service is named `asr-crawler`; image builds and the
  container entrypoint is `asr-crawler`.
- [ ] `asr-crawler --config deploy/dev/config.yaml --once --dry-run` loads clean.
- [ ] All four `config.yaml` files load without warnings introduced by this epic;
  `logging.app_log_file` writes `asr-crawler.log`.
- [ ] `CLAUDE.md`, `README.md`, `docs/architecture/overview.md` use `asr-crawler`
  / `asr_crawler` throughout.
- [ ] `.claude/settings.json` permission entry references `asr_crawler`.
- [ ] A pre-[[EPIC-043]] `<watch_dir>/.whispercrawl/state.db` is still migrated to
  `<config dir>/db/state.db` on first run (regression test unchanged).

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
