# EPIC-015: Fix Diarization — Speaker Labels in Transcript

**Status**: Planned

## Goal

Make diarization actually produce speaker-labelled transcripts. Currently
`diarize: true` has no visible effect on the `.txt` output.

## Diagnosis

Two separate bugs found by inspecting `_diarize.json` output from EPIC-014:

### Bug 1 — Wrong output format

The transcriber requests `output=txt` from whisper-asr-webservice. The `txt`
format is plain text — speaker labels are **never included** regardless of
whether diarization ran. Even if the service correctly assigns speakers, the
information is silently discarded before the file is written.

**Fix**: when `diarize: true`, request `output=json`, read the per-segment
`speaker` field, and format the transcript as:

```
[SPEAKER_00]: First segment text.
[SPEAKER_01]: Second segment text.
```

### Bug 2 — Silent diarization failure (missing HuggingFace token)

whisperx uses [pyannote.audio](https://github.com/pyannote/pyannote-audio)
for speaker diarization, which requires accepting a licence on HuggingFace and
providing a token via the `HF_TOKEN` environment variable in the whisper
container. Without it the service silently returns segments with no `speaker`
field.

Evidence: `_diarize.json` segment keys are
`{start, end, text, tokens, avg_logprob, …}` — no `speaker` key anywhere.

**Fix**:
- Document `HF_TOKEN` requirement in `docker-compose.dev.yml` and README.
- When the transcriber detects that all segments lack a `speaker` field,
  log a `WARNING` so the misconfiguration is immediately visible in logs.

## Scope

### Config

No new config flags. Behaviour changes only when `diarize: true`.

### Transcriber changes

When `diarize: true`:

1. Request `output=json` instead of `output=txt`.
2. Parse the JSON response.
3. Build the transcript string from segments:
   - If segment has `speaker`: `[{speaker}]: {text}\n`
   - If segment has no `speaker` (diarization failed): use `{text}\n`
     and emit one `WARNING` log message per file.
4. Return the formatted string. Downstream pipeline is unchanged.

The `diarize_log` feature (EPIC-014) continues to work: the same JSON
response body is saved to `_diarize.json` (no second HTTP request needed
when `output=json` is already the primary format — see Tasks).

### Docker / config changes

`docker-compose.dev.yml` — add `HF_TOKEN` to the whisper service environment:

```yaml
whisper:
  environment:
    ASR_MODEL: large
    ASR_ENGINE: whisperx
    HF_TOKEN: ${HF_TOKEN:-}   # required for speaker diarization
```

`docker/.env.example` — add `HF_TOKEN=` with a comment pointing to HuggingFace.

`config/config.yaml` — add a comment on the `diarize` line explaining the
HuggingFace token requirement.

`README.md` — add a note under the dev quickstart about obtaining and setting
`HF_TOKEN`.

### Side-effect: diarize_log optimisation

Because the primary request now uses `output=json`, the `diarize_log` path
(EPIC-014) no longer needs a second HTTP request — the JSON body is already
available. Reuse the response body for the sidecar file instead of making
a second call.

## Files to change

- `src/fileswhisper/pipeline/transcriber.py`
  - When `diarize: true`: use `output=json`, parse segments, format text
  - Warn when no `speaker` fields detected
  - When `diarize_log: true`: write JSON body from the primary response
    (no second request)
- `docker/docker-compose.dev.yml` — add `HF_TOKEN` env var to whisper service
- `docker/.env.example` — add `HF_TOKEN=` entry
- `config/config.yaml` — add HuggingFace token comment on `diarize` line
- `README.md` — document `HF_TOKEN` setup

## Acceptance Criteria

- [ ] When `diarize: true` and whisperx returns speaker labels, `.txt` contains
  lines like `[SPEAKER_00]: text`
- [ ] When `diarize: true` but no speaker labels returned (missing token),
  transcript is plain text and a `WARNING` is logged mentioning HF_TOKEN
- [ ] When `diarize: false`, behaviour is unchanged (output=txt, no JSON parsing)
- [ ] `diarize_log: true` still writes `_diarize.json` without a second HTTP request
- [ ] `docker-compose.dev.yml` passes `HF_TOKEN` through to whisper container
- [ ] README documents the HuggingFace token requirement
- [ ] Tests cover: speakers present (formatted output), no speakers (plain text +
  warning), diarize=false (unchanged path)

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
