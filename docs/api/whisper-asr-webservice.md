# whisper-asr-webservice API

Docs: https://ahmetoner.com/whisper-asr-webservice/
Default local URL: `http://localhost:9000`

## Transcription + Diarization Endpoint

```
POST /asr
Content-Type: multipart/form-data
```

Key parameters:

| Parameter | Type | Notes |
|---|---|---|
| `audio_file` | file | Audio/video file to transcribe |
| `task` | string | `transcribe` or `translate` |
| `language` | string | `ru`, `en`, `auto`, etc. |
| `output` | string | `txt`, `json`, `vtt`, `srt`, `tsv` |
| `diarize` | bool | Enable speaker diarization |
| `min_speakers` | int | Min speaker count (diarization) |
| `max_speakers` | int | Max speaker count (diarization) |

## Response

Plain text (when `output=txt`) or structured JSON. With diarization, JSON includes speaker labels.

## Diarization support by engine

`whisperx` and `gigaam` both diarize via pyannote.audio — set `diarize: true` on
the engine and provide `HF_TOKEN` to the ASR container (accept the
[pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
licence first). `faster_whisper` and `openai_whisper` do not diarize; `diarize`
is ignored for them and transcripts carry no `[SPEAKER_XX]` labels.

## Multiple engines (EPIC-048)

`transcription.engines` in `config.yaml` is a list of engine configs — each one
maps to a single `/asr` service (its own `url`, `language`, `diarize`, params).
whispercrawl calls every configured engine for every file and keeps their
outputs separate (`<file>_<name>.<ext>`, `_<dirname>_<name>.<ext>`, and separate
processing-index rows). It does not use any multi-model feature of a single
service — run one `whisper-asr-webservice` per engine.

The dev stack runs two instances out of the box (EPIC-054): `asr-webservice` on
host port 9000 (`ASR_ENGINE=whisperx`, `ASR_MODEL=tiny`) and `asr-webservice2` on
9001 (`ASR_ENGINE=gigaam`, `ASR_MODEL=v1_rnnt`, `ASR_REQUEST_LOGGING=true`), wired
as the `whisperx` / `gigaam` engines in `deploy/dev/config.yaml`. Override the
models/engines via `ASR_MODEL(2)` / `ASR_ENGINE(2)` / `ASR_REQUEST_LOGGING2` in
`deploy/dev/.env`. Both engines diarize (`diarize: true` on the base block), so
both `asr-webservice` containers get `HF_TOKEN`.

## `ASR_MODEL`

For `whisperx`, `faster_whisper`, and `openai_whisper`, `ASR_MODEL` is a Whisper
model name:

- Standard models: `tiny`, `base`, `small`, `medium`, `large-v1`, `large-v2`,
  `large-v3` (or `large`), `large-v3-turbo` (or `turbo`)
- English-optimized models: `tiny.en`, `base.en`, `small.en`, `medium.en`
- Distilled models: `distil-large-v2`, `distil-medium.en`, `distil-small.en`,
  `distil-large-v3` (only for `whisperx` and `faster_whisper`)

For English-only applications the `.en` models tend to perform better, especially
`tiny.en` and `base.en`; the difference is smaller for `small.en` / `medium.en`.
The distilled models trade a little accuracy for faster inference.

For the `gigaam` engine (Russian-focused, from
[GigaAM](https://github.com/salute-developers/GigaAM)), `ASR_MODEL` is a GigaAM
model name instead:

- Short names (aliased to the `v3_*` models below): `rnnt` (default), `ctc`,
  `e2e_rnnt`, `e2e_ctc`
- Russian-only models: `v1_rnnt`, `v1_ctc`, `v2_rnnt`, `v2_ctc`, `v3_rnnt`,
  `v3_ctc`, `v3_e2e_rnnt`, `v3_e2e_ctc`
- Multilingual models (CTC only): `multilingual_ctc`, `multilingual_large_ctc`
- A local filesystem path to a fine-tuned `.ckpt` checkpoint

GigaAM also ships `*_ssl` (self-supervised pretraining: `v1_ssl`, `v2_ssl`,
`v3_ssl`, `multilingual_ssl`, `multilingual_large_ssl`) and `emo` (emotion
recognition) model names, but those aren't speech-to-text models and aren't
usable with this engine's transcription pipeline.

## Docker (dev)

```yaml
# See deploy/dev/docker-compose.dev.yml — asr-webservice (:9000) and asr-webservice2 (:9001)
image: ${ASR_IMAGE:-asr-webservice:latest}   # mirrored from onerahmet/openai-whisper-asr-webservice:latest
```
