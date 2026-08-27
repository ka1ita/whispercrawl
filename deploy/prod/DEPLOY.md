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
sudo bash setup.sh
```

`setup.sh` creates `.env` (from `.env.example`), creates `audio/` and `logs/`, loads the Docker image, and — when run as root — creates a system user/group matching the container's `appuser` (uid/gid `1000` by default, see `APP_UID`/`APP_GID` in `.env`) and `chown`s `audio/`, `logs/`, and `config.yaml` to it so the non-root container can read/write the mounted paths. If you can't run it as root, it prints the exact `sudo` commands to run manually instead.

When run interactively, `setup.sh` prompts for the install directory (default: wherever `setup.sh` lives — press Enter to accept). To skip the prompt, pass it explicitly or set `INSTALL_DIR`:

```bash
bash setup.sh /opt/whispercrawl
# or
INSTALL_DIR=/opt/whispercrawl bash setup.sh
```

Bind mounts are labeled `:Z` in `docker-compose.prod.yml` for SELinux-enforcing hosts (e.g. RedOS 8); this is a no-op where SELinux isn't active.

---

## 2. Configure

```bash
# Service URLs (created by setup.sh from .env.example)
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
bash service-cleanup.sh

# Dry run — shows what would be deleted
bash service-cleanup.sh --dry-run
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

## Processing index

`whispercrawl` keeps a persisted index of processed files at `audio/.whispercrawl/state.db`
(SQLite). It lets each scheduled run skip files it has already handled without re-scanning
the whole tree, and lets an interrupted run resume where it left off.

- **Safe to delete.** The next run rebuilds it from whichever output files exist — nothing is reprocessed.
- **Backups:** either include `audio/.whispercrawl/` or deliberately exclude it; losing it only costs one slower "rediscovery" run.
- Disable with `state.enabled: false` in `config.yaml`. Set `max_files_per_run` to cap how many
  files each run processes when first draining a large backlog.

---

## Directory layout

```text
deploy/prod/
  dist/               ← whispercrawl.tar (transfer from build host)
  audio/              ← mount point for audio/video files (created by setup.sh)
  audio/.whispercrawl/state.db  ← persisted processing index (auto-created; safe to delete)
  logs/               ← mount point for log output (created by setup.sh)
  .env                ← WHISPER_URL, OLLAMA_URL, APP_UID/APP_GID (created from .env.example by setup.sh)
  .env.example        ← template for .env
  config.yaml         ← pipeline configuration
  docker-compose.prod.yml
  setup.sh            ← first-run setup (create dirs, load image, fix ownership/permissions)
  service-start.sh    ← docker compose up -d
  service-down.sh     ← docker compose down
  service-cleanup.sh  ← docker compose run --rm whispercrawl --once --cleanup
  DEPLOY.md           ← this file
```
