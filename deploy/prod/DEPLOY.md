# Production Deployment — whispercrawl

This directory is the complete production deployment bundle. Transfer it to the target host and follow the steps below.

**Prerequisite:** Docker and Docker Compose must be installed on the target host.

---

## 1. Transfer and install

On the **build host** (internet-connected), export the image:

```bash
# From repo root
bash deploy/dev/build-prod.sh
```

This places `whispercrawl.tar` in `deploy/prod/dist/`. Transfer the entire `deploy/prod/` directory to the target host, then run setup:

```bash
cd /path/to/deploy/prod
bash setup.sh
```

`setup.sh` creates `audio/` and `logs/` directories and loads the Docker image.

---

## 2. Configure

```bash
# Service URLs
cp .env.example .env
vi .env          # set WHISPER_URL and OLLAMA_URL

# Pipeline settings (language, model, schedule, etc.)
vi config.yaml
```

---

## 3. Verify (dry run)

```bash
docker compose -f docker-compose.prod.yml run --rm whispercrawl --once --dry-run
```

No API calls are made — it only logs the files that would be processed.

---

## 4. Run once

```bash
docker compose -f docker-compose.prod.yml run --rm whispercrawl --once
```

---

## 5. Run as a scheduled service

```bash
# Start in background
bash service-start.sh

# Stop
bash service-down.sh
```

---

## 6. Cleanup output files

Remove all pipeline output files (`.txt`, `_fix.txt`, `_sum.txt`) without touching source audio:

```bash
docker compose -f docker-compose.prod.yml run --rm whispercrawl --once --cleanup

# Dry run — shows what would be deleted
docker compose -f docker-compose.prod.yml run --rm whispercrawl --once --cleanup --dry-run
```

---

## 7. Restart after config change

```bash
# Config is mounted read-only — restart picks up changes
docker compose -f docker-compose.prod.yml restart whispercrawl

# Full recreate (after image update)
docker compose -f docker-compose.prod.yml up -d --force-recreate whispercrawl
```

---

## 8. Monitor

```bash
# Tail live logs
docker compose -f docker-compose.prod.yml logs -f whispercrawl

# Last 100 lines
docker compose -f docker-compose.prod.yml logs --tail=100 whispercrawl

# Container status
docker compose -f docker-compose.prod.yml ps

# Application log file
tail -f logs/whispercrawl.log

# Structured service request log
tail -f logs/service_requests.ndjson
```

---

## Directory layout

```text
deploy/prod/
  dist/               ← whispercrawl.tar (transfer from build host)
  audio/              ← mount point for audio/video files (created by setup.sh)
  logs/               ← mount point for log output (created by setup.sh)
  .env                ← WHISPER_URL, OLLAMA_URL (create from .env.example)
  .env.example        ← template for .env
  config.yaml         ← pipeline configuration
  docker-compose.prod.yml
  setup.sh            ← first-run setup (create dirs, load image)
  service-start.sh    ← docker compose up -d
  service-down.sh     ← docker compose down
  DEPLOY.md           ← this file
```
