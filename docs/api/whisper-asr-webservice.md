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

## Docker (dev)

```yaml
# See deploy/dev/docker-compose.dev.yml
image: onerahmet/openai-whisper-asr-webservice:latest
```
