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
| `whisper.tar` | asr-webservice:latest (mirrored from onerahmet/openai-whisper-asr-webservice:latest) |
| `ollama.tar` | ollama/ollama:latest |

If the target host can reach an internal Docker registry, set `ASR_IMAGE` in
`.env` to the mirrored path (e.g. `registry.example/asr-webservice:latest`) and
the `whisper` service will pull it instead of loading `whisper.tar`.

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
sudo bash setup.sh
```

`setup.sh` will:

- Copy `.env.example` → `.env` (if `.env` does not yet exist)
- Create `audio/`, `logs/`, and `db/` directories
- Load all three Docker images from `dist/`
- When run as root: create a system user/group matching the `whispercrawl` container's `appuser` (uid/gid `1000` by default, see `APP_UID`/`APP_GID` in `.env`) and `chown` `audio/`, `logs/`, `db/`, and `config.yaml` to it, so the non-root container can read/write the mounted paths. If not run as root, it prints the exact `sudo` commands to run manually instead.

When run interactively, `setup.sh` prompts for the install directory (default: wherever `setup.sh` lives — press Enter to accept). To skip the prompt, pass it explicitly or set `INSTALL_DIR`:

```bash
bash setup.sh /opt/whispercrawl
# or
INSTALL_DIR=/opt/whispercrawl bash setup.sh
```

Bind mounts are labeled `:Z` in `docker-compose.prod-local.yml` for SELinux-enforcing hosts (e.g. RedOS 8); this is a no-op where SELinux isn't active.

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

Each processed file leaves one result (`<file>.<ext>`) and each directory one
(`_<dirname>.<ext>`). Cleanup removes those plus any pre-EPIC-047 sidecars
(`_fix` / `_sum` / `_all` / `_concat`), without touching source audio:

```bash
docker compose -f docker-compose.prod-local.yml run --rm whispercrawl --once --cleanup

# Dry run — shows what would be deleted
docker compose -f docker-compose.prod-local.yml run --rm whispercrawl --once --cleanup --dry-run
```

**Upgrading a pre-EPIC-047 catalog:** run the cleanup once, then re-run with
`--refresh` (or `rescan: true`) to regenerate results in the single-file form.

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

## Processing index

`whispercrawl` keeps a persisted index of processed files at `db/state.db`
(SQLite; mounted into the container at `/db`). It lets each scheduled run skip files it has
already handled without re-scanning the whole tree, and lets an interrupted run resume where
it left off. `setup.sh` creates and `chown`s the `db/` directory.

- **Safe to delete.** The next run rebuilds it from whichever output files exist — nothing is reprocessed
  (but stored transcript text is lost, so `--refresh` will re-transcribe any deleted file on the next normal run).
- **Backups:** either include `db/` or deliberately exclude it; losing it only costs one slower "rediscovery" run.
- **Upgrading from an older release:** an existing `audio/.whispercrawl/state.db` is moved into
  `db/` automatically on the first run (best-effort; a failure just starts a fresh index).
- Disable with `state.enabled: false` in `config.yaml`. Set `max_files_per_run` to cap how many
  files each run processes when first draining a large backlog.
- **Stored transcript text.** With `state.store_text: true` (default) the index also keeps each
  file's raw ASR transcript and post-processed text, enabling:

  ```bash
  docker compose -f docker-compose.prod-local.yml run --rm whispercrawl --refresh
  ```

  `--refresh` re-runs post-processing, summarization, and formatting for every already-processed
  file from the stored transcript, with the current `config.yaml`, and **without a single whisper
  call** — the fast way to apply a new fix prompt, summary model, or output format. A file whose
  source changed, or that has no stored transcript, is skipped. Needs
  `state.enabled: true` and `state.store_text: true`; changing `transcription:` settings still
  requires `rescan: true`.
- **Checking for failures.** A failing step records the error in the index instead of writing a
  `<file>_err.txt` beside the audio. List outstanding failures with:

  ```bash
  docker compose -f docker-compose.prod-local.yml run --rm whispercrawl --errors
  ```

  It prints each failure grouped by path and **exits non-zero** when any are outstanding — suitable
  for a monitoring wrapper. A failure clears itself once that file / directory next succeeds. On
  upgrade from a pre-EPIC-049 build, `--once --cleanup` sweeps the leftover `_err.txt` files. With
  `state.enabled: false` the `<file>_err.txt` sidecar behavior is unchanged.

---

## Directory layout

```text
deploy/prod-local/
  dist/                         ← image tars (transfer from build host)
  audio/                        ← mount point for audio/video files (created by setup.sh)
  db/state.db                   ← persisted processing index (auto-created; safe to delete)
  logs/                         ← mount point for log output (created by setup.sh)
  .env                          ← HF_TOKEN, ASR_MODEL, APP_UID/APP_GID (created from .env.example by setup.sh)
  .env.example                  ← template for .env
  config.yaml                   ← pipeline configuration
  docker-compose.prod-local.yml
  setup.sh                      ← first-run setup (load images, create dirs, fix ownership/permissions)
  service-start.sh              ← docker compose up -d
  service-down.sh               ← docker compose down
  DEPLOY.md                     ← this file
```
