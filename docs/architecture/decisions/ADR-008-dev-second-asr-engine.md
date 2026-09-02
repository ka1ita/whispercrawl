# ADR-008: Dev Stack Runs Two ASR Engines With a Dedicated `deploy/dev/config.yaml`

**Date**: 2026-09-02
**Status**: Accepted

## Context

[ADR-004](ADR-004-multiple-asr-engines.md) / EPIC-048 made `transcription.engines`
a first-class feature, but nothing in the dev environment exercised it. Both dev
compose files defined one `whisper` service on `9000:9000`, the dev stack mounted
the project-root `config.yaml`, and the dev local-python wrappers passed
`--config config.yaml`. The only place to add a dev `engines:` list was the
committed single-engine example — editing it there pollutes the example and
churns git every time an operator wants to compare two engines.

## Decision

- **A second ASR container `whisper2`** on host port **9001** (`9001:9000`
  internally) in both `deploy/dev/docker-compose.dev.yml` and
  `docker-compose.services.yml`. Its `ASR_ENGINE` defaults to `gigaam`
  (`ASR_MODEL=v1_rnnt`, `ASR_REQUEST_LOGGING=true`) — a *different* engine from
  `whisper`'s `whisperx` — so the two transcripts actually differ and the
  comparison is meaningful. Own `whisper2_cache` volume; shares `hf_cache` with
  `whisper`. Both services now read `ASR_MODEL(2)` / `ASR_ENGINE(2)` from env
  with these values as defaults.
- **A committed `deploy/dev/config.yaml`** — the dev copy of the root example,
  with `transcription.engines` pre-wired to `whisperx` (`${WHISPER_URL:…:9000}`)
  and `gigaam` (`${WHISPER2_URL:…:9001}`). Shared settings
  (`language`, `diarize`, `speaker_timestamps`, `timeout`) stay on the base
  block per ADR-004's merge semantics. The project-root `config.yaml` is
  untouched and stays the single-engine working example.
- **Env-var URL indirection.** The engine URLs default to `127.0.0.1:9000` /
  `127.0.0.1:9001`, which is what local-python + `docker-compose.services.yml`
  need (host ports). The all-in-Docker `docker-compose.dev.yml` overrides
  `WHISPER_URL` / `WHISPER2_URL` to the internal `http://whisper:9000` /
  `http://whisper2:9000`. One config file, both dev modes.
- The dev `whispercrawl` service mounts `./config.yaml` (i.e.
  `deploy/dev/config.yaml`); `app-python.sh` / `app-python-once.sh` /
  `app-python-cleanup.sh` pass `--config deploy/dev/config.yaml`.

Deployment artifacts and one config template only — no `src/` or test changes.

## Alternatives considered

- **Edit the root `config.yaml` for dev.** Rejected — it is the committed
  single-engine example; a dev `engines:` list there is misleading and noisy in
  diffs.
- **A `docker-compose.dev.override.yml` that adds `whisper2`.** More moving
  parts than a second service block, and it still needs a dev config with the
  engine list — which is the real deliverable.
- **Same `ASR_ENGINE` on both services.** Pointless — two identical engines
  produce (near-)identical transcripts; the comparison needs them to differ.
- **`faster_whisper` as the second engine.** Was the initial default; switched
  to `gigaam` (`v1_rnnt`) — a purpose-built Russian model — since the dev
  material is Russian-language and the whisperx/faster_whisper comparison is
  narrower than whisperx-vs-GigaAM.
- **prod / prod-local get a second engine too.** Out of scope — they keep the
  single `whisper` service and the commented `engines:` example. A second prod
  engine is a separate epic if ever needed.
- **Automatic model pull for `whisper2`** (an `ollama-init`-style helper).
  Unnecessary — `whisper-asr-webservice` fetches its model on first request.

## Consequences

- `deploy/dev/services-docker-start.sh` (and the full stack) now start two ASR
  containers; first-run model downloads happen twice and the two caches are
  separate volumes.
- A dev run writes `<file>_whisperx.<ext>` **and** `<file>_gigaam.<ext>` beside
  each recording, plus `_<dirname>_whisperx.<ext>` / `_<dirname>_gigaam.<ext>`
  per directory — two sets of outputs, each independently `--refresh`-able.
- `deploy/dev/config.yaml` is now a maintained file: changes to the root example
  that should also apply to dev must be mirrored (the two are intentionally
  independent — the root file has no `engines:` list).
- Both engines diarize (`gigaam`, like `whisperx`, runs pyannote), so the
  `whisper2` container also needs `HF_TOKEN` — the compose files already pass it.
  Both engines inherit `diarize: true` / `speaker_timestamps: true` from the base
  block, so both produce `[SPEAKER_XX HH:MM:SS]` labels.
