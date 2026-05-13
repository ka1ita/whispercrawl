# EPIC-010: Application Log File

**Status**: Done

## Goal

Write the application's console log (INFO/WARNING/ERROR lines currently going only to stdout) to a rotating text file so the service can be monitored and debugged in production without a terminal attached.

## Background

`main.py` calls `logging.basicConfig(...)` which directs all log output to stderr/stdout. In production (RedOS 8 systemd service) there is no persistent terminal; operators need the log in a file they can `tail`, ship to a log aggregator, or rotate. The existing `logging.log_file` field is for the structured service-interaction ndjson and is separate from this.

## Scope

- Add `app_log_file`, `app_log_level`, `app_log_max_bytes`, `app_log_backup_count` to `LoggingConfig`
- Implement `setup_logging(config: LoggingConfig)` in a new `src/fileswhisper/utils/logging_setup.py`
  - Always attaches a `StreamHandler` (console)
  - When `app_log_file` is set, also attaches a `RotatingFileHandler` (auto-creates parent directory)
  - `app_log_level` controls both handlers (default `INFO`)
  - `app_log_max_bytes` and `app_log_backup_count` configure rotation (defaults: 10 MB / 5 backups)
- Replace `logging.basicConfig(...)` in `main.py` with `setup_logging(config.logging)`
- Update `config/config.example.yaml` with new fields
- Write unit tests for `setup_logging`

## Config Interface

```yaml
logging:
  app_log_file: ./logs/fileswhisper.log   # omit to log to console only
  app_log_level: INFO                      # DEBUG | INFO | WARNING | ERROR
  app_log_max_bytes: 10485760              # 10 MB per file
  app_log_backup_count: 5                  # keep last 5 rotated files
```

## Acceptance Criteria

- [x] When `app_log_file` is set, log lines are written to that file in addition to console
- [x] Parent directory of `app_log_file` is created automatically if it doesn't exist
- [x] Log rotates at `app_log_max_bytes` and keeps `app_log_backup_count` backups
- [x] `app_log_level` controls the minimum level for both handlers
- [x] When `app_log_file` is absent, behaviour is identical to current (console only)
- [x] Unit tests cover: file handler attached, directory creation, level respected, console-only fallback

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
