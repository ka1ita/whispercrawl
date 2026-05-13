# EPIC-009: Enhanced Service Logging

**Status**: Done

## Goal

Enrich the service interaction log with full HTTP context — method, URL, request params and body, response body — and move the log file to a dedicated service-managed directory instead of requiring a manual `log_file` path in config.

## Background

Currently `ServiceLogger` writes a minimal summary entry (timestamp, service, model, duration, status code, response size). This is enough for performance tracking but not for debugging: the actual prompt sent to ollama, the whisper query params, and the LLM response text are invisible. The `log_file` path must also be set manually, which is friction.

## Scope

### 1 — Auto-managed log directory

- Add `log_dir: Optional[str]` to `LoggingConfig` (e.g. `logs/service/`)
- `ServiceLogger` creates the directory if it doesn't exist and writes `service_requests.ndjson` there automatically
- Keep `log_file` for explicit path override; `log_dir` takes precedence if both are set
- If neither is set and `requests: true`, default to `logs/service_requests.ndjson` relative to `watch_dir`

### 2 — Full request/response logging

Extend the ndjson entry with:

| Field | Content |
| --- | --- |
| `method` | HTTP method (`POST`, `GET`) |
| `url` | Full request URL |
| `params` | Query-string params dict (whisper `language`, `task`, `engine`, etc.) |
| `request_body` | For ollama: `{"model": ..., "messages": [...]}` — text only, no binary |
| `response_body` | Parsed response text/JSON — for ollama: `message.content`; for whisper: transcript text |

Binary `audio_file` multipart content is **never** logged.

### 3 — Text truncation

- Add `max_text_length: Optional[int]` to `LoggingConfig` (default `None` = unlimited)
- `ServiceLogger` truncates `request_body` text fields and `response_body` to `max_text_length` characters, appending `…` when cut
- Applied to: ollama prompt messages, ollama response content, whisper transcript text
- Never applied to structured fields (URL, params, status code, etc.)

### 4 — Caller changes

Update `Transcriber`, `PostProcessor`, and `Summarizer` to pass the extra context to `ServiceLogger.log()`.

## Config Interface

```yaml
logging:
  requests: true
  log_dir: ./logs/          # directory — file named service_requests.ndjson
  # log_file: ./custom.ndjson  # explicit path override (overrides log_dir)
  max_text_length: 500      # truncate request/response text fields (null = unlimited)
```

## Log Entry Shape

```json
{
  "timestamp": "2026-05-11T12:06:34Z",
  "service": "whisper",
  "method": "POST",
  "url": "http://localhost:9000/asr",
  "params": {"task": "transcribe", "language": "ru", "engine": "whisperx"},
  "file": "meeting.ogg",
  "model": "large",
  "duration_s": 74.932,
  "status_code": 200,
  "response_body": "Добрый день...",
  "response_size_bytes": 875
}
```

## Acceptance Criteria

- [x] `log_dir` config creates the directory and writes `service_requests.ndjson` inside it
- [x] `log_file` still works as an explicit override
- [x] When neither is set and `requests: true`, log defaults to `<watch_dir>/logs/service_requests.ndjson`
- [x] Each entry includes `method`, `url`, `params`, `request_body`, `response_body`
- [x] Binary audio content is never written to the log
- [x] `max_text_length` truncates `request_body` and `response_body` text, appending `…`
- [x] `max_text_length: null` (default) writes full text without truncation
- [x] Unit tests cover new entry fields, `log_dir` path creation, and truncation behaviour

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
