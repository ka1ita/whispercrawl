# EPIC-021: prod-local — All-in-One Single-Server Deployment

**Status**: Done

## Goal

Add a `deploy/prod-local/` bundle that runs **all services** (whisper-asr-webservice, ollama, and whispercrawl) on a single server using Docker Compose — targeting air-gapped Linux hosts that have no internet access.

Extend `deploy/dev/build-prod.sh` to export all three Docker images into `deploy/prod/dist/` (and `deploy/prod-local/dist/`) so operators can transfer and load them offline.

## Background

`deploy/prod/` covers the case where whisper and ollama are hosted externally.  
A common alternative is a single server that runs everything; today there is no compose file for that case and the build script only saves the `whispercrawl` image.

The dev compose (`deploy/dev/docker-compose.dev.yml`) already defines all three services and is the reference for image names, environment variables, and volume conventions.

---

## Scope

### `deploy/prod-local/` — Single-server all-in-one bundle

**Directory layout:**

```text
deploy/prod-local/
  dist/                    ← filled by build-prod.sh; contains all image tars
  config.yaml              ← production config template (watch_dir already set, service URLs point to internal network)
  .env.example             ← ASR_MODEL, HF_TOKEN vars
  docker-compose.prod-local.yml
  setup.sh                 ← load all images from dist/, create runtime dirs, print next steps
  service-start.sh         ← docker compose up -d
  service-down.sh          ← docker compose down
  DEPLOY.md                ← operator manual for single-server setup
```

**`docker-compose.prod-local.yml`** — adapt from `deploy/dev/docker-compose.dev.yml`:

- `whisper` service: image `onerahmet/openai-whisper-asr-webservice:latest` (loaded offline), env vars from `.env`, volumes for cache
- `ollama` service: image `ollama/ollama:latest` (loaded offline), volume for models
- `whispercrawl` service: image `whispercrawl:latest`, internal service URLs (`http://whisper:9000`, `http://ollama:11434`), volumes for audio/logs/config, `depends_on` whisper and ollama
- All services: `restart: unless-stopped`

**`setup.sh` responsibilities:**

1. Load all three images from `dist/`: `whispercrawl.tar`, `whisper.tar`, `ollama.tar`
2. Create `audio/`, `logs/` directories
3. Copy `.env.example` → `.env` if `.env` does not yet exist
4. Print next steps: edit `.env` (set `HF_TOKEN`, `ASR_MODEL`), edit `config.yaml`, run `service-start.sh`

**`service-start.sh`:** `docker compose -f docker-compose.prod-local.yml up -d`

**`service-down.sh`:** `docker compose -f docker-compose.prod-local.yml down`

**`DEPLOY.md`:** operator manual covering prerequisites, transfer, load, configuration, first-run model pull, and service management.

---

### `deploy/dev/build-prod.sh` — export all images

Extend the existing script to also save `onerahmet/openai-whisper-asr-webservice:latest` and `ollama/ollama:latest` into `deploy/prod/dist/` and `deploy/prod-local/dist/` alongside `whispercrawl.tar`.

New images to export:

| Local image | Output filename |
| --- | --- |
| `whispercrawl:latest` | `whispercrawl.tar` |
| `onerahmet/openai-whisper-asr-webservice:latest` | `whisper.tar` |
| `ollama/ollama:latest` | `ollama.tar` |

The script should pull each image with `docker pull` before saving if it is not already present locally (so the build machine only needs Docker, not a running compose stack).

---

## Acceptance Criteria

- [ ] `deploy/prod-local/` exists with: `docker-compose.prod-local.yml`, `setup.sh`, `service-start.sh`, `service-down.sh`, `config.yaml`, `.env.example`, `DEPLOY.md`, `dist/.gitkeep`
- [ ] `docker-compose.prod-local.yml` defines whisper, ollama, and whispercrawl services on a shared network; service URLs are internal (no `${WHISPER_URL}` substitution needed)
- [ ] `setup.sh` loads all three image tars; creates `audio/`, `logs/`; prints clear next-step instructions; idempotent
- [ ] `service-start.sh` / `service-down.sh` work from any working directory (paths relative to script location)
- [ ] `build-prod.sh` saves `whispercrawl.tar`, `whisper.tar`, and `ollama.tar` into `deploy/prod/dist/` and `deploy/prod-local/dist/`
- [ ] All scripts: `set -euo pipefail`, executable bit, paths resolved relative to `$SCRIPT_DIR`
- [ ] `DEPLOY.md` covers: prerequisites, file transfer, `setup.sh` run, first-run ollama model pull, `.env` config, start/stop

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
