# Production Deployment — whispercrawl (all-in-one, single server)

This bundle runs **whisper-asr-webservice**, **ollama**, and **whispercrawl** on a single host using Docker Compose. No internet access is required on the target host after initial setup.

**Prerequisite:** Docker and Docker Compose must be installed on the target host.

---

## 1. Build and export images (build host)

On the **build host** (internet-connected), from the repository root:

```bash
bash deploy/dev/build-prod.sh
```

This builds `whispercrawl:latest`, then pulls and exports all three images into both `deploy/prod/dist/` and `deploy/prod-local/dist/`:

| File | Image |
|---|---|
| `whispercrawl.tar` | whispercrawl:latest |
| `whisper.tar` | onerahmet/openai-whisper-asr-webservice:latest |
| `ollama.tar` | ollama/ollama:latest |

---

## 2. Transfer to target host

Transfer the entire `deploy/prod-local/` directory to the target host:

```bash
rsync -av deploy/prod-local/ user@host:/opt/whispercrawl/
# or
scp -r deploy/prod-local/ user@host:/opt/whispercrawl/
```

---

## 3. Run setup

```bash
cd /opt/whispercrawl
bash setup.sh
```

`setup.sh` will:
- Load all three Docker images from `dist/`
- Create `audio/` and `logs/` directories
- Copy `.env.example` → `.env` (if `.env` does not yet exist)

---

## 4. Configure

```bash
# Set HF_TOKEN (required for diarization) and ASR_MODEL
vi .env

# Review language, model, schedule, and pipeline settings
vi config.yaml
```

Key `.env` values:

| Variable | Description |
|---|---|
| `HF_TOKEN` | HuggingFace token for pyannote diarization model. Create at https://huggingface.co/settings/tokens and accept the [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) license. |
| `ASR_MODEL` | Whisper model size: `tiny` \| `base` \| `small` \| `medium` \| `large`. Larger = more accurate, more RAM. |

---

## 5. Pull the ollama model (first run)

The ollama container needs at least one model before whispercrawl can use it. This step requires internet access on the target host (or a pre-seeded `ollama_data` Docker volume):

```bash
# Start just ollama first
docker compose -f docker-compose.prod-local.yml up -d ollama

# Pull the model configured in config.yaml (default: gemma3:1b)
docker compose -f docker-compose.prod-local.yml exec ollama ollama pull gemma3:1b
```

---

## 6. Verify (dry run)

```bash
docker compose -f docker-compose.prod-local.yml run --rm whispercrawl --once --dry-run
```

No API calls are made — it only logs the files that would be processed.

---

## 7. Run once

```bash
docker compose -f docker-compose.prod-local.yml run --rm whispercrawl --once
```

---

## 8. Run as a scheduled service

```bash
# Start all services in background
bash service-start.sh

# Stop all services
bash service-down.sh
```

---

## 9. Cleanup output files

Remove all pipeline output files without touching source audio:

```bash
docker compose -f docker-compose.prod-local.yml run --rm whispercrawl --once --cleanup

# Dry run — shows what would be deleted
docker compose -f docker-compose.prod-local.yml run --rm whispercrawl --once --cleanup --dry-run
```

---

## 10. Restart after config change

```bash
# Config is mounted read-only — restart picks up changes
docker compose -f docker-compose.prod-local.yml restart whispercrawl

# Full recreate (after image update)
docker compose -f docker-compose.prod-local.yml up -d --force-recreate whispercrawl
```

---

## 11. Monitor

```bash
# Tail live logs (all services)
docker compose -f docker-compose.prod-local.yml logs -f

# whispercrawl only
docker compose -f docker-compose.prod-local.yml logs -f whispercrawl

# Container status
docker compose -f docker-compose.prod-local.yml ps

# Application log file
tail -f logs/whispercrawl.log

# Structured service request log
tail -f logs/service_requests.ndjson
```

---

## Directory layout

```text
deploy/prod-local/
  dist/                         ← image tars (transfer from build host)
  audio/                        ← mount point for audio/video files (created by setup.sh)
  logs/                         ← mount point for log output (created by setup.sh)
  .env                          ← HF_TOKEN, ASR_MODEL (created from .env.example by setup.sh)
  .env.example                  ← template for .env
  config.yaml                   ← pipeline configuration
  docker-compose.prod-local.yml
  setup.sh                      ← first-run setup (load images, create dirs)
  service-start.sh              ← docker compose up -d
  service-down.sh               ← docker compose down
  DEPLOY.md                     ← this file
```
