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

## Multiple engines (EPIC-048)

`transcription.engines` in `config.yaml` is a list of engine configs — each one
maps to a single `/asr` service (its own `url`, `language`, `diarize`, params).
whispercrawl calls every configured engine for every file and keeps their
outputs separate (`<file>_<name>.<ext>`, `_<dirname>_<name>.<ext>`, and separate
processing-index rows). It does not use any multi-model feature of a single
service — run one `whisper-asr-webservice` per engine.

## Docker (dev)

```yaml
# See deploy/dev/docker-compose.dev.yml
image: ${ASR_IMAGE:-asr-webservice:latest}   # mirrored from onerahmet/openai-whisper-asr-webservice:latest
```
