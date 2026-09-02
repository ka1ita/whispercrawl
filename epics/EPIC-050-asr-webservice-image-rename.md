# EPIC-050: Pull the ASR Service Image from the Internal Registry (`asr-webservice:latest`)

**Status**: Done (2026-09-02)

## Goal

Every Compose file, build script, and deployment doc currently names the ASR
service image as the public Docker Hub tag
`onerahmet/openai-whisper-asr-webservice:latest`. Production runs on air-gapped
RedOS hosts that have no Docker Hub access; the image is instead mirrored to an
**internal registry**. After this epic the project refers to that image as
`asr-webservice:latest` (registry host supplied per-environment), and nothing
pulls the `onerahmet/...` name.

The image contents are unchanged — this is a rename plus a registry-host
indirection, not a fork or a custom Dockerfile.

## Problem Description

`onerahmet/openai-whisper-asr-webservice:latest` is hard-coded in five places
(from `grep -rn onerahmet`):

- [deploy/dev/docker-compose.services.yml:14](../deploy/dev/docker-compose.services.yml#L14) — `whisper` service
- [deploy/dev/docker-compose.dev.yml:19](../deploy/dev/docker-compose.dev.yml#L19) — `whisper` service
- [deploy/prod-local/docker-compose.prod-local.yml:15](../deploy/prod-local/docker-compose.prod-local.yml#L15) — `whisper` service
- [deploy/dev/build-prod.sh:28](../deploy/dev/build-prod.sh#L28) — `WHISPER_IMAGE=...` (pulled, then `docker save`d to `whisper.tar`)
- [deploy/prod-local/DEPLOY.md:22](../deploy/prod-local/DEPLOY.md#L22) — image-manifest table

plus doc references:

- [docs/api/whisper-asr-webservice.md:42](../docs/api/whisper-asr-webservice.md#L42) — dev Docker snippet
- [epics/EPIC-021-prod-local-all-in-one.md](../epics/EPIC-021-prod-local-all-in-one.md) lines 40, 62, 69, 82 — historical scope text

Consequences:

- On an air-gapped host, a `docker compose pull` or a fresh `up` against any of
  the compose files tries Docker Hub and fails; the only reason `prod-local`
  works today is that `setup.sh` pre-loads `whisper.tar` and Compose happens to
  find the matching name locally.
- `build-prod.sh` pulls from Docker Hub on the build host — fine there, but the
  saved tar carries the `onerahmet/...` repo tag, so the name leaks into every
  downstream host and can never be re-pulled from the internal mirror by that
  name.
- There is no single knob for "which registry / tag is the ASR image" — a site
  with its own mirror path (`registry.corp.local/asr-webservice:1.7.0`) has to
  edit three compose files.

## Scope

### 1. Image name + registry indirection

Introduce one Compose variable, `ASR_IMAGE`, defaulting to `asr-webservice:latest`:

```yaml
  whisper:
    image: ${ASR_IMAGE:-asr-webservice:latest}
```

- A site that pulls straight from its mirror sets
  `ASR_IMAGE=registry.corp.local/asr-webservice:latest` in its `.env`.
- A site that `docker load`s a tar (the `prod-local` air-gap flow) leaves the
  default — `build-prod.sh` retags the saved image to `asr-webservice:latest`
  so the loaded name matches.
- The service key stays `whisper`, the internal hostname stays `whisper:9000`,
  and `transcription.url` / `WHISPER_URL` are unchanged — only the image ref
  moves.

Apply to all three compose files:

- `deploy/dev/docker-compose.services.yml`
- `deploy/dev/docker-compose.dev.yml`
- `deploy/prod-local/docker-compose.prod-local.yml`

### 2. `deploy/dev/build-prod.sh`

- `WHISPER_IMAGE` becomes two values: `ASR_SRC_IMAGE` (what the build host
  pulls — default `onerahmet/openai-whisper-asr-webservice:latest`, overridable
  by env for a site that already mirrors it) and `ASR_IMAGE`
  (`asr-webservice:latest`, the canonical name everything else uses).
- After pulling `ASR_SRC_IMAGE`, `docker tag "$ASR_SRC_IMAGE" "$ASR_IMAGE"`.
- `docker save` exports `$ASR_IMAGE` (not the source tag) to `whisper.tar`, so
  the tar carries the `asr-webservice:latest` repo tag.
- The `LOCAL_IMAGES` map value for `whisper.tar` becomes `$ASR_IMAGE`.
- Console/`echo` text updated to say `asr-webservice:latest`.

### 3. `.env.example` files

- `deploy/prod-local/.env.example`: add a commented `ASR_IMAGE` entry explaining
  the default (`asr-webservice:latest`, loaded from `dist/whisper.tar` by
  `setup.sh`) and that a site with an internal registry can point it at
  `registry.example/asr-webservice:<tag>` to `docker compose pull` instead.
- `deploy/prod/.env.example`: no change — that bundle connects to an external
  ASR URL and runs no ASR container.

### 4. `deploy/prod-local/setup.sh`

- No logic change — it still `docker load -i dist/whisper.tar`. Add a one-line
  comment that the tar now loads as `asr-webservice:latest` and that setting
  `ASR_IMAGE` in `.env` to a registry path makes the load step optional.

### 5. Docs

- `deploy/prod-local/DEPLOY.md`:
  - image-manifest table: `whisper.tar` → `asr-webservice:latest`
    (mirrored from `onerahmet/openai-whisper-asr-webservice:latest`).
  - a note in the setup section on the `ASR_IMAGE` override for hosts that can
    reach an internal registry.
- `deploy/prod/DEPLOY.md`: no image change; it already only sets `WHISPER_URL`.
- `docs/api/whisper-asr-webservice.md`: the Docker snippet uses
  `image: asr-webservice:latest  # mirrored from onerahmet/openai-whisper-asr-webservice`.
- `docs/architecture/overview.md`: already labels the box `asr-webservice`
  ([overview.md:18](../docs/architecture/overview.md#L18)) — no change needed;
  confirm no stray `onerahmet` reference.
- `README.md`: keeps the upstream project link (attribution); no image tag to
  change there.
- `CLAUDE.md`: add a line under **Target Environments** / dev-services notes that
  the ASR image is referenced as `asr-webservice:latest` (`ASR_IMAGE` override),
  mirrored from the upstream `onerahmet/...` image.
- `epics/EPIC-021-prod-local-all-in-one.md`: leave the body as the historical
  record; append a single italic note under the status line saying the image was
  renamed to `asr-webservice:latest` in EPIC-050, rather than rewriting its
  acceptance criteria.

### 6. `docker-compose.dev.yml` env-file wiring

`deploy/dev/docker-compose.dev.yml` and `docker-compose.services.yml` are run
with `--env-file deploy/dev/.env` per CLAUDE.md. Add a commented `ASR_IMAGE=`
line to `deploy/dev/.env.example` so a dev who mirrors the image locally can
override it; the default resolves without any `.env` entry.

## Files to change

- `deploy/dev/docker-compose.services.yml`
- `deploy/dev/docker-compose.dev.yml`
- `deploy/prod-local/docker-compose.prod-local.yml`
- `deploy/dev/build-prod.sh`
- `deploy/dev/.env.example`
- `deploy/prod-local/.env.example`
- `deploy/prod-local/setup.sh` (comment only)
- `deploy/prod-local/DEPLOY.md`
- `docs/api/whisper-asr-webservice.md`
- `docs/architecture/overview.md` (verify only)
- `CLAUDE.md`
- `epics/EPIC-021-prod-local-all-in-one.md` (one-line note)

No source code (`src/`) or test changes — this is deployment-artifact only.

## Acceptance Criteria

- [x] `grep -rn "onerahmet/openai-whisper-asr-webservice"` returns only:
  the upstream attribution in `README.md` (project link, not an image tag),
  the `ASR_SRC_IMAGE` default in `build-prod.sh`, the "mirrored from" comments,
  and the EPIC-021 historical body.
- [x] All three compose files reference `${ASR_IMAGE:-asr-webservice:latest}`;
  `docker compose -f <file> config` resolves the image to `asr-webservice:latest`
  with no `.env`, and to the override when `ASR_IMAGE` is set (both verified).
- [x] `deploy/dev/build-prod.sh` pulls `ASR_SRC_IMAGE`, `docker tag`s it to
  `asr-webservice:latest`, and `docker save`s that tag to `whisper.tar` so a
  downstream `docker load` yields `asr-webservice:latest` (`bash -n` clean;
  full run needs Docker + network on a build host).
- [x] On a host with `dist/whisper.tar`, `bash setup.sh` + `bash service-start.sh`
  brings up the `whisper` service with zero network pulls (image name now
  matches the compose default).
- [x] Setting `ASR_IMAGE=registry.example/asr-webservice:latest` in
  `deploy/prod-local/.env` makes `docker compose config` (and `pull whisper`)
  target that registry.
- [x] `deploy/prod-local/DEPLOY.md` image table and `docs/api/whisper-asr-webservice.md`
  show `asr-webservice:latest`.
- [x] `deploy/prod/` bundle is untouched (still external-URL only).
- [x] No `src/` or test changes — `pytest` / `ruff check` unaffected.

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).

## Out of Scope

- **A custom ASR Dockerfile** (baked-in models, tweaks). This epic only renames
  and re-registries the existing upstream image.
- **Pinning a non-`latest` tag.** Sites can do that via `ASR_IMAGE`; the default
  stays `:latest` to match today's behavior.
- **`ollama/ollama:latest`.** Same air-gap concerns exist but Ollama is a
  separate change; not touched here.
- **Renaming the Compose service key** from `whisper` to `asr` — churny, breaks
  `whisper:9000` internal DNS in every config, no functional gain.
- **Automating the mirror push** (`onerahmet/...` → internal registry). That is
  an ops runbook step, not a repo artifact.
