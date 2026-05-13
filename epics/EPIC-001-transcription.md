# EPIC-001: Transcription & Diarization

**Status**: Done

## Goal

Implement recursive audio/video file discovery and transcription via `whisper-asr-webservice`, producing a `.txt` file beside each source file.

## Scope

- `src/fileswhisper/file_walker.py` — recursive scan with skip-processed / full-rescan modes
- `src/fileswhisper/pipeline/transcriber.py` — POST to whisper API, handle response
- Language detection from filename (`_ru`, `_en`, `_auto`) with config fallback
- Write output to `<source><suffix>.txt` only on success; write `<source>_err.txt` on failure
- Config section: `transcription` (URL, model, language, output suffix)

## Acceptance Criteria

- [x] Given an audio file `meeting_ru.mp3`, the service calls whisper with `language=ru`
- [x] Given a file with no language suffix, the config default language is used
- [x] If the `.txt` already exists and mode is `skip-processed`, the file is skipped
- [x] On whisper API error, `_err.txt` is written and the next file continues
- [x] Output includes diarization speaker labels when `diarize: true` in config

## Tasks

See [tasks/backlog.md](../tasks/backlog.md) for granular task breakdown.
