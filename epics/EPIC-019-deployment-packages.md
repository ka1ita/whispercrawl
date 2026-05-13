# EPIC-019: Deployment Packages for Prod and Dev

**Status**: Done

## Goal

Organise all deployment artefacts into two self-contained directory bundles — one for production (air-gapped) and one for development (internet-connected) — so that operators can copy a single directory to the target host and have everything they need to install, start, and stop the service.

## Background

Relevant Docker infrastructure already exists:

| Artefact | Current location |
|---|---|
| `fileswhisper` image export | `docker/export-image.sh` → `docker/dist/fileswhisper.tar` |
| Image import | `docker/import-image.sh` |
| Prod compose | `docker/docker-compose.prod.yml` |
| Dev compose (external services) | `docker/docker-compose.dev.yml` |
| Prod deploy manual | `docs/deploy/docker-prod.md` |

These artefacts are scattered across the repo; operators must understand the repo layout to find them. The goal is to assemble them (or thin wrappers around them) into `deploy/prod/` and `deploy/dev/` so each bundle is self-sufficient.

---

## Scope

### `deploy/prod/` — Air-gap production bundle

Everything needed to install and operate the service on a host without internet access.

**Directory layout:**

```text
deploy/prod/
  dist/                    ← symlink or copy placeholder; filled by export-image.sh
  config.yaml              ← production config template (watch_dir, service URLs, schedule)
  setup.sh                 ← creates runtime dirs, loads Docker image from dist/
  service-start.sh         ← docker compose up -d
  service-down.sh          ← docker compose down
  docker-compose.prod.yml  ← copy / symlink of docker/docker-compose.prod.yml
  DEPLOY.md                ← operator manual (moved from docs/deploy/docker-prod.md)
```

**`setup.sh` responsibilities:**

1. Create `audio/`, `logs/`, `config/` directories under install path
2. Load Docker image: `docker load -i dist/fileswhisper.tar`
3. Print next steps (configure `config.yaml`, then run `service-start.sh`)

**`service-start.sh`:** `docker compose -f docker-compose.prod.yml up -d`

**`service-down.sh`:** `docker compose -f docker-compose.prod.yml down`

**`DEPLOY.md`:** move content from `docs/deploy/docker-prod.md`; update `docs/deploy/docker-prod.md` to a redirect stub pointing to the new location.

**`config.yaml`:** prod-ready template with placeholder URLs and `/audio`, `/logs` paths already set; no dev-only keys.

---

### `deploy/dev/` — Internet-connected dev bundle

Convenience scripts for developers running the full stack on a workstation.

**Directory layout:**

```text
deploy/dev/
  start.sh             ← start all services (external services + fileswhisper)
  stop.sh              ← stop all services
  rebuild.sh           ← rebuild fileswhisper image and restart its container
  start-external.sh    ← start only whisper + ollama (docker-compose.services.yml)
```

**`start-external.sh`:** `docker compose -f ../../docker/docker-compose.services.yml up -d`

**`start.sh`:** calls `start-external.sh`, then starts fileswhisper via `docker-compose.dev.yml`

**`stop.sh`:** `docker compose -f ../../docker/docker-compose.dev.yml down`

**`rebuild.sh`:** `docker compose -f ../../docker/docker-compose.dev.yml up -d --build fileswhisper`

Scripts use relative paths from their own location so they work when invoked directly (`bash deploy/dev/start.sh`) or via absolute path.

---

### `docker/export-image.sh` — update output path

After building, copy `docker/dist/fileswhisper.tar` into `deploy/prod/dist/` automatically, so the prod bundle is ready to transfer immediately.

---

## Acceptance Criteria

- [ ] `deploy/prod/` exists and contains: `setup.sh`, `service-start.sh`, `service-down.sh`, `docker-compose.prod.yml`, `config.yaml`, `DEPLOY.md`, `dist/.gitkeep`
- [ ] `setup.sh` creates `audio/`, `logs/`, `config/` dirs and loads the image; prints clear next-step instructions
- [ ] `service-start.sh` / `service-down.sh` work when invoked from any working directory
- [ ] `DEPLOY.md` contains full operator manual (content moved from `docs/deploy/docker-prod.md`); old file becomes a redirect stub
- [ ] `deploy/dev/` exists and contains: `start.sh`, `stop.sh`, `rebuild.sh`, `start-external.sh`
- [ ] All dev scripts are idempotent and resolve paths relative to the script location (not `$PWD`)
- [ ] `docker/export-image.sh` copies the built tar into `deploy/prod/dist/` after saving
- [ ] All scripts are executable (`chmod +x`) and have `set -euo pipefail`

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
