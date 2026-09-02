# EPIC-054: Dev Stack — Second ASR Service on :9001 and a Dedicated `deploy/dev/config.yaml`

**Status**: Landed 2026-09-02. See [ADR-008](../docs/architecture/decisions/ADR-008-dev-second-asr-engine.md).

## Goal

Make the two-engine path from [[EPIC-048]] runnable in the dev environment out
of the box:

- a **second `whisper-asr-webservice`** container in the dev compose files,
  published on host port **9001** (the first stays on 9000);
- a **dedicated `deploy/dev/config.yaml`** — a copy of the project-root
  `config.yaml` — that declares `transcription.engines` for both services and is
  the config the dev stack and the dev local-python wrappers use.

The project-root `config.yaml` stays the single-engine working example
(unchanged). Dev-specific engine wiring lives in `deploy/dev/config.yaml` only.

## Depends on

[[EPIC-048]] (landed) — `transcription.engines`, per-engine results and index
rows. This epic is **deployment artifacts + a config template only**: no `src/`
or test-suite changes.

Related: [[EPIC-012]] (docker environments), [[EPIC-050]] (ASR image rename),
[[EPIC-017]] (config at project root), [[EPIC-038]] (deploy config/permissions).

## Problem Description

- Both dev compose files (`deploy/dev/docker-compose.dev.yml`,
  `deploy/dev/docker-compose.services.yml`) define exactly one `whisper` service
  on `9000:9000`. Comparing two ASR engines/models needs a second endpoint, and
  today an operator has to hand-add a service and a second config every time.
- The dev stack mounts `../../config.yaml` and the dev local-python wrappers
  (`app-python.sh`, `app-python-once.sh`) pass `--config config.yaml`. The only
  place to configure a dev-only `engines:` list is the root file, which is the
  committed single-engine example — editing it for dev pollutes the example and
  churns git.
- The commented `engines:` block in every config template points both entries at
  `localhost:9000` / `localhost:9001`, but nothing in dev actually serves 9001.

## Scope

### 1. `deploy/dev/docker-compose.dev.yml` — second ASR service

- Add service `whisper2` mirroring `whisper`:
  - `image: ${ASR_IMAGE:-asr-webservice:latest}` (same override as `whisper`);
  - `ports: ["9001:9000"]`;
  - `environment`: `ASR_MODEL: ${ASR_MODEL2:-tiny}`,
    `ASR_ENGINE: ${ASR_ENGINE2:-faster_whisper}` (a *different* engine from
    `whisper` by default so the two results differ — the whole point),
    `HF_TOKEN`, `HF_HUB_DISABLE_TELEMETRY: true`;
  - its own named volumes (`whisper2_cache:/root/.cache/whisper`, reuse the
    shared `hf_cache` for the pyannote model);
  - `restart: unless-stopped`.
- `whisper` gains explicit `ASR_MODEL: ${ASR_MODEL:-tiny}` /
  `ASR_ENGINE: ${ASR_ENGINE:-whisperx}` so both services read from env
  symmetrically (no behaviour change when the vars are unset).
- `whispercrawl` service:
  - mount `../config.yaml` **→** `deploy/dev/config.yaml`:
    `- ./config.yaml:/config.yaml:ro` (path is relative to the compose file's
    directory, i.e. `deploy/dev/`).
  - `environment`: add `WHISPER2_URL: http://whisper2:9000`; keep
    `WHISPER_URL: http://whisper:9000`.
  - `depends_on`: add `whisper2: { condition: service_started }`.
- `volumes:` — add `whisper2_cache:`.

### 2. `deploy/dev/docker-compose.services.yml` — second ASR service

- Same `whisper2` service as above (published `9001:9000`, own
  `whisper2_cache`, shared `hf_cache`).
- Same explicit `ASR_MODEL` / `ASR_ENGINE` env on `whisper`.
- No `whispercrawl` service here (this file is services-only) — the local
  process reads `deploy/dev/config.yaml`, whose engine URLs default to
  `127.0.0.1:9000` / `127.0.0.1:9001`.
- `volumes:` — add `whisper2_cache:`.

### 3. `deploy/dev/config.yaml` — dedicated dev config (new file)

- Start as a verbatim copy of the project-root `config.yaml`.
- Replace the single flat `transcription:` engine URL usage with a real
  `engines:` list (keep the shared settings — `language`, `diarize`,
  `speaker_timestamps`, `timeout` — on the base block, [[EPIC-048]] merge
  semantics):

  ```yaml
  transcription:
    language: ru
    diarize: true
    speaker_timestamps: true
    timeout: 3600
    engines:
      - name: whisperx
        url: ${WHISPER_URL:http://127.0.0.1:9000}
      - name: faster
        url: ${WHISPER2_URL:http://127.0.0.1:9001}
        diarize: false            # faster_whisper has no diarization
  ```

  - `127.0.0.1` not `localhost` — the existing Windows/IPv6 multipart-stall note
    in `config.yaml` applies here too; carry that comment over.
  - The `${WHISPER_URL:…}` / `${WHISPER2_URL:…}` defaults make the file work
    as-is for **local python + `docker-compose.services.yml`** (host ports
    9000/9001); the dev **all-in-Docker** stack overrides both vars to the
    internal `http://whisper:9000` / `http://whisper2:9000`.
- Everything else (formatter, result, postprocessing, summarization, logging,
  schedule) copied unchanged. `watch_dir`, `app_log_file`, `log_dir` keep the
  `${WATCH_DIR:…}` / `${LOGS_DIR:…}` forms already in the root file.
- Header comment: "Dev config — two ASR engines (see EPIC-054). The
  project-root config.yaml stays the single-engine example."
- This file **is committed** (like `deploy/prod/config.yaml` and
  `deploy/prod-local/config.yaml`). Confirm `.gitignore` does not catch it
  (`*.txt`/`*.html` rules don't; `config/config.*.local.yaml` doesn't) — add an
  explicit allow only if a rule is found to match.

### 4. Dev wrapper scripts

- `deploy/dev/app-python.sh`, `deploy/dev/app-python-once.sh`,
  `deploy/dev/app-python-cleanup.sh`: change `--config config.yaml` →
  `--config deploy/dev/config.yaml` (still run from `REPO_ROOT`). Update the
  usage comment ("two ASR engines on :9000 and :9001; start them with
  `services-docker-start.sh`").
- `deploy/dev/services-docker-start.sh` /
  `services-docker-restart.sh` / `services-docker-stop.sh`: echo lines mention
  `whisper :9000` **and** `whisper2 :9001`.
- `deploy/dev/app-docker-start.sh`: echo line notes both ASR services.
- No change to `docker-rebuild.sh` / `app-docker-stop.sh` beyond comments.

### 5. `deploy/dev/.env` and `.env.example`

- `.env.example`: add commented defaults with explanation —
  ```
  # Dev runs two ASR services (EPIC-054): whisper on :9000, whisper2 on :9001.
  # ASR_MODEL   / ASR_ENGINE   configure the first  (default tiny / whisperx)
  # ASR_MODEL2  / ASR_ENGINE2  configure the second (default tiny / faster_whisper)
  # ASR_MODEL=tiny
  # ASR_ENGINE=whisperx
  # ASR_MODEL2=tiny
  # ASR_ENGINE2=faster_whisper
  ```
  Keep the existing `HF_TOKEN` / `ASR_IMAGE` entries.
- `.env`: leave the operator's real `HF_TOKEN` / `ASR_IMAGE` untouched; no new
  required vars (all have compose defaults).

### 6. Docs

- `CLAUDE.md`:
  - "Commands" — the dev-services / dev-stack start commands note the second ASR
    endpoint on 9001 and that dev uses `deploy/dev/config.yaml`.
  - Where `config.yaml` is described as "the working example" — add that
    `deploy/dev/config.yaml` is the dev copy with `engines:` pre-wired.
- `docs/architecture/overview.md` — the dev-environment note / any compose
  description gains `whisper2` on 9001.
- `docs/architecture/decisions/` — short ADR: dev gets a committed two-engine
  config (a separate file, not an override of the root example); second engine
  defaults to a different `ASR_ENGINE` so the comparison is meaningful; host
  port 9001; env-var URL indirection so one config serves both dev modes.
- `README.md` — if it lists dev quickstart ports, add 9001.
- `docs/api/whisper-asr-webservice.md` — note the dev stack runs two instances.

## Files to change

- `deploy/dev/docker-compose.dev.yml` — `whisper2` service, `whisper2_cache`
  volume, `whispercrawl` config mount + `WHISPER2_URL` + `depends_on`.
- `deploy/dev/docker-compose.services.yml` — `whisper2` service + volume.
- `deploy/dev/config.yaml` — **new**, dev two-engine config.
- `deploy/dev/app-python.sh`, `app-python-once.sh`, `app-python-cleanup.sh` —
  `--config deploy/dev/config.yaml`.
- `deploy/dev/services-docker-start.sh`, `services-docker-restart.sh`,
  `services-docker-stop.sh`, `app-docker-start.sh` — echo text.
- `deploy/dev/.env.example` — `ASR_MODEL(2)` / `ASR_ENGINE(2)` comments.
- `CLAUDE.md`, `docs/architecture/overview.md`,
  `docs/architecture/decisions/ADR-008-dev-second-asr-engine.md` (new),
  `README.md`, `docs/api/whisper-asr-webservice.md`.

## Acceptance Criteria

- [x] `docker compose -f deploy/dev/docker-compose.dev.yml config` resolves two
  ASR services — `whisper` (`9000:9000`) and `whisper2` (`9001:9000`) — each
  with its own whisper cache volume, sharing `hf_cache`.
- [x] `docker compose -f deploy/dev/docker-compose.services.yml config` likewise
  resolves both ASR services.
- [x] The dev `whispercrawl` service mounts `deploy/dev/config.yaml` at
  `/config.yaml` (not the project-root file) and sets `WHISPER_URL` /
  `WHISPER2_URL` to the internal `whisper` / `whisper2` names.
- [x] `deploy/dev/config.yaml` loads without error (`whispercrawl --config
  deploy/dev/config.yaml --once --dry-run`) and resolves
  `config.transcription.engines` to two entries (`whisperx`, `faster`) with the
  expected URLs; with no env vars set the URLs are `127.0.0.1:9000` /
  `127.0.0.1:9001`.
- [x] A dev run against both services writes `<file>_whisperx.<ext>` and
  `<file>_faster.<ext>` beside each audio file and
  `_<dirname>_whisperx.<ext>` / `_<dirname>_faster.<ext>` per directory, with
  independent index rows (existing EPIC-048 behaviour — smoke-check only).
- [x] `deploy/dev/app-python.sh` / `app-python-once.sh` /
  `app-python-cleanup.sh` pass `--config deploy/dev/config.yaml`.
- [x] Project-root `config.yaml` is unchanged.
- [x] `deploy/dev/config.yaml` is tracked by git.
- [x] `bash -n` clean on every edited script; `docker compose … config` clean on
  both dev compose files with and without `deploy/dev/.env`.
- [x] Docs mention the second ASR service on 9001 and the dedicated dev config.

## Out of Scope

- **`src/` changes.** Multi-engine support is entirely EPIC-048; this epic only
  wires dev to use it.
- **prod / prod-local compose files.** They keep the single `whisper` service
  and the commented `engines:` example. A second prod engine is a separate epic
  if ever needed.
- **Automatic model pull for `whisper2`.** `whisper-asr-webservice` fetches its
  model on first request like `whisper` does; no `ollama-init`-style helper.
- **Running the two engines concurrently.** Still sequential per EPIC-048's
  "Out of Scope".
- **Choosing / merging the better transcript across engines.** Downstream
  concern, not this epic.
- **A third+ engine or making the engine count configurable in compose.** Two
  fixed services; more is a manual edit.
