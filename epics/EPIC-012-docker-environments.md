# EPIC-012: Docker Environments

**Status**: Done

## Goal

Provide a ready-to-use Docker setup for every deployment scenario: full local dev (everything in Compose), lightweight dev (only filesWhisper in Docker, external services on the host), and production (service-only container connecting to external whisper and Ollama). All variants mount audio and config from the host so no rebuild is needed to change them.

## Background

The repo already has `docker/docker-compose.dev.yml` that starts whisper-asr-webservice and Ollama, but it does not include a filesWhisper container at all. There is no `Dockerfile` for the service, no production compose file, and no guidance for the scenario where whisper/Ollama run on the host while filesWhisper runs in Docker.

## Environments

| Name | File | filesWhisper | whisper | Ollama |
|---|---|---|---|---|
| **Dev 2** (all-in-Docker) | `docker/docker-compose.dev2.yml` | container | container | container |
| **Dev 1** (service only) | `docker/docker-compose.dev1.yml` | container | host (`localhost`) | host (`localhost`) |
| **Production** | `docker/docker-compose.prod.yml` | container | external URL | external URL |

## Scope

### Dockerfile (`docker/Dockerfile`)
- Multi-stage build: `builder` installs deps via `pip install --no-deps`, `runtime` copies site-packages only
- Base image: `python:3.11-slim`
- Runs as non-root user (`appuser`)
- Entry point: `fileswhisper --config /config/config.yaml`
- No source files in the image — only the installed package

### Volumes (all compose files)
- `/audio` → host directory with audio/video files (`watch_dir` must be `/audio` in config)
- `/config` → host directory containing `config.yaml`
- `/logs` → host directory for application and service logs

### docker-compose.dev2.yml (Dev 2 — all in Docker)
- Inherits whisper + ollama services from existing `docker-compose.dev.yml`
- Adds `fileswhisper` service built from `docker/Dockerfile`
- `depends_on: [whisper, ollama]`
- Config must point `transcription.url` to `http://whisper:9000` and `postprocessing.url` to `http://ollama:11434`

### docker-compose.dev1.yml (Dev 1 — external host services)
- Only `fileswhisper` service
- Uses `extra_hosts: ["host.docker.internal:host-gateway"]` for host access
- Config points to `http://host.docker.internal:9000` and `http://host.docker.internal:11434`

### docker-compose.prod.yml (Production)
- Only `fileswhisper` service
- URLs passed via environment variables `WHISPER_URL` and `OLLAMA_URL` (referenced in config with `${WHISPER_URL}`)
- `restart: unless-stopped`

### Air-gap export script (`docker/export-images.sh`)
- Builds filesWhisper image and saves it alongside whisper and ollama to tar files
- Companion `docker/import-images.sh` loads them on the target host
- Both scripts document the manual Ollama model-file copy step

### README update
- Replace current "Production (air-gapped)" section with per-environment quick-start instructions
- Add `docker/` directory structure overview

## Config Interface

```yaml
# config for Dev 2 / docker-compose.dev2.yml
watch_dir: /audio

transcription:
  url: http://whisper:9000

postprocessing:
  url: http://ollama:11434

logging:
  app_log_file: /logs/fileswhisper.log
  log_dir: /logs/
```

```yaml
# config for Production — uses env-var substitution
watch_dir: /audio

transcription:
  url: ${WHISPER_URL}

postprocessing:
  url: ${OLLAMA_URL}
```

## Acceptance Criteria

- [x] `docker/Dockerfile` builds successfully; resulting image runs `fileswhisper --once --dry-run` against a mounted config
- [x] `docker-compose.dev2.yml` starts all three services; filesWhisper container exits cleanly on `--once`
- [x] `docker-compose.dev1.yml` starts filesWhisper only; connects to host services via `host.docker.internal`
- [x] `docker-compose.prod.yml` starts filesWhisper only; `WHISPER_URL` / `OLLAMA_URL` env vars override service URLs
- [x] All compose files mount `/audio`, `/config`, `/logs` volumes
- [x] `docker/export-images.sh` produces tar files for all three images; `import-images.sh` loads them
- [x] README updated with per-environment quickstart and `docker/` layout

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
