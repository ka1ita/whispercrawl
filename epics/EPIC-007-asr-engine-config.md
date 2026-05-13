# EPIC-007: ASR Engine Configuration

**Status**: Done

## Goal

Expose whisper-asr-webservice engine selection and engine-specific parameters in the `transcription` config section so users can tune the backend without editing service environment variables.

## Background

whisper-asr-webservice supports multiple ASR backends via the `ASR_ENGINE` environment variable (`openai_whisper`, `faster_whisper`, `whisperx`). The `/asr` endpoint accepts several query parameters that differ by engine. Currently filesWhisper hard-codes no engine-specific params, leaving those capabilities unreachable.

## Scope

- `src/fileswhisper/config.py` — add `asr_engine`, `initial_prompt`, `vad_filter`, `word_timestamps`, `encode` to `TranscriptionConfig`
- `src/fileswhisper/pipeline/transcriber.py` — pass non-None config values as query params in the `/asr` POST request
- `config/config.example.yaml` — document new fields with allowed values
- `tests/test_pipeline/test_transcriber.py` — unit tests for param forwarding

## New `TranscriptionConfig` Fields

| Field | Type | Default | ASR param |
| --- | --- | --- | --- |
| `asr_engine` | `str \| None` | `None` | `engine` |
| `initial_prompt` | `str \| None` | `None` | `initial_prompt` |
| `vad_filter` | `bool \| None` | `None` | `vad_filter` |
| `word_timestamps` | `bool \| None` | `None` | `word_timestamps` |
| `encode` | `bool \| None` | `None` | `encode` |

`None` values are omitted from the request (server default applies).

## Acceptance Criteria

- [x] `asr_engine: faster_whisper` in config causes `engine=faster_whisper` to be sent in the `/asr` request
- [x] `initial_prompt`, `vad_filter`, `word_timestamps`, `encode` are forwarded when set, omitted when `None`
- [x] Config loads correctly when new fields are absent (full backwards compatibility)
- [x] Unit tests cover: all params present, all params absent, mixed None/set

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
