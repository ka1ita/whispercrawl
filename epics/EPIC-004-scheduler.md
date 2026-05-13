# EPIC-004: Scheduler & CLI

**Status**: Done

## Goal

Run the full pipeline on a configurable schedule, with support for one-shot invocation.

## Scope

- `src/fileswhisper/scheduler.py` — wraps pipeline in APScheduler cron job
- `src/fileswhisper/main.py` — CLI entry point
- Config section: `schedule` (cron expression or interval)

## CLI Interface

```
fileswhisper [OPTIONS]

Options:
  --config PATH   Path to config file (default: config.yaml)
  --once          Run once and exit (ignore schedule)
  --dry-run       Log which files would be processed without processing them
```

## Acceptance Criteria

- [x] Service starts and runs on configured schedule (e.g. every 30 minutes)
- [x] `--once` flag runs the pipeline once and exits with code 0 on success
- [x] `--dry-run` logs files that would be processed without calling any external service
- [x] Graceful shutdown on SIGTERM / SIGINT
- [x] Schedule config supports both cron expressions and simple intervals (`30m`, `1h`)

## Tasks

See [tasks/backlog.md](../tasks/backlog.md).
