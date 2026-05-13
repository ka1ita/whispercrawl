# EPIC-020: Rename Project to WhisperCrawl

**Status**: Done

## Goal

Rename the project from `filesWhisper` / `fileswhisper` to `WhisperCrawl` / `whispercrawl` across all artefacts — source package, CLI entrypoint, Docker image, compose services, docs, and config — so that the new name is consistently reflected everywhere.

## Background

The original name `filesWhisper` describes implementation mechanics (file + Whisper ASR). `WhisperCrawl` better reflects the product identity: it crawls directories and processes audio via Whisper. The rename touches the Python package, the CLI command, Docker image tags, compose service names, config files, and documentation.

---

## Scope

### Python package

- Rename `src/fileswhisper/` → `src/whispercrawl/`
- Update all internal imports: `from fileswhisper.` → `from whispercrawl.`
- Update `pyproject.toml`: `name`, `packages` find directive, and `[project.scripts]` entrypoint (`fileswhisper` → `whispercrawl`)

### Docker

- Rename the Docker image: `fileswhisper` → `whispercrawl`
- Rename the compose service: `fileswhisper` → `whispercrawl` in all compose files (`deploy/dev/docker-compose.dev.yml`, `deploy/prod/docker-compose.prod.yml`)
- Update `deploy/prod/build-prod.sh` (image name references)
- Update any `docker load` / `docker save` calls that hard-code the image name

### Config and scripts

- Update `deploy/prod/config.yaml` if it contains the old name
- Update `deploy/dev/` scripts that reference the service name

### Documentation

- `CLAUDE.md`: update all references (`fileswhisper` → `whispercrawl`, commands, paths)
- `README.md`: update all references
- `docs/`: update any mentions of the old name
- Epic and task files: no retroactive edits needed; new work uses the new name

### Repository root

The working directory (`c:\_Project\filesWhisper`) is outside scope for this epic — renaming the host directory is an operator action, not a code change.

---

## Acceptance Criteria

- [ ] `src/whispercrawl/` exists; `src/fileswhisper/` is removed
- [ ] All Python imports use `whispercrawl`
- [ ] `pyproject.toml` names the package `whispercrawl` and exposes the `whispercrawl` CLI command
- [ ] `pip install -e .` succeeds and `whispercrawl --help` works
- [ ] `pytest` passes without import errors
- [ ] Docker image is built and tagged as `whispercrawl`; compose service is named `whispercrawl`
- [ ] `ruff check src tests` reports no errors
- [ ] `CLAUDE.md` and `README.md` use the new name throughout

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
