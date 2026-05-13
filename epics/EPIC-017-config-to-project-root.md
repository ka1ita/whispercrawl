# EPIC-017: Move config.yaml to Project Root

**Status**: Planned

## Goal

Move `config/config.yaml` to the project root so that the config file sits
alongside `pyproject.toml`, `CLAUDE.md`, and docker-compose files. Eliminate
the `config/` directory entirely.

## Background

The `config/` directory contains only one file (`config.yaml`). Having a
dedicated directory for a single file adds indirection without benefit. Placing
`config.yaml` at the project root is more conventional, simplifies Docker
volume mounts (one file instead of a directory), and matches the default path
already expected by the CLI (`--config config.yaml`).

## Scope

### Files to move

- `config/config.yaml` → `config.yaml` (project root)
- Delete the now-empty `config/` directory

### Python changes

- `src/fileswhisper/main.py` — default `--config` path is already
  `Path("config.yaml")`, which matches the new location; no change needed
  when running from the project root. Verify and update any inline comments
  or docs if needed.

### Docker changes

| File | Current | After |
|------|---------|-------|
| `docker/Dockerfile` | `ENTRYPOINT ["fileswhisper", "--config", "/config/config.yaml"]` | `ENTRYPOINT ["fileswhisper", "--config", "/config.yaml"]` |
| `docker/docker-compose.dev.yml` | `- ../config:/config:ro` (volume) | `- ../config.yaml:/config.yaml:ro` |
| `docker/docker-compose.prod.yml` | `- ./config:/config:ro` (volume) | `- ./config.yaml:/config.yaml:ro` |
| `docker/Dockerfile` | `VOLUME ["/audio", "/config", "/logs"]` | `VOLUME ["/audio", "/logs"]` — remove `/config` |

### Documentation changes

- `CLAUDE.md` — update references from `config/config.yaml` to `config.yaml`
- `docs/deploy/docker-prod.md` — update any volume mount examples
- Any other docs that mention `config/config.yaml`

### What is NOT in scope

- Changing config file format or content
- Supporting multiple config files
- Changing how environment variable expansion works inside the config

## Acceptance Criteria

- [ ] `config.yaml` exists at the project root; `config/` directory is gone
- [ ] `fileswhisper --config config.yaml --once --dry-run` works when run from
  the project root (Windows dev environment)
- [ ] `docker compose -f docker/docker-compose.dev.yml run --rm fileswhisper --once`
  works after the volume mount change
- [ ] `docker compose -f docker/docker-compose.prod.yml run --rm fileswhisper --once`
  works after the volume mount change
- [ ] No references to `config/config.yaml` remain in docs, Dockerfiles, or
  compose files
- [ ] `CLAUDE.md` and relevant docs updated

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
