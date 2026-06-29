# EPIC-032: Immediate First Run on Service Start

## Goal

Run the pipeline once immediately when the service starts, then continue running on the configured schedule. Currently the first execution is delayed until the first scheduled trigger fires.

## Problem Description

When the service starts in scheduler mode, the first pipeline run is deferred until the cron expression or interval triggers. For long intervals (e.g. `1h` or `0 */4 * * *`) this means new files sit unprocessed for up to the full interval after every restart or deployment.

The fix is simple: run the pipeline once synchronously before handing control to the scheduler, so startup always processes the current backlog immediately.

## Scope

### 1. `scheduler.py` — `start_scheduler`

After registering the job but before calling `scheduler.start()`, call `run_pipeline(config)` directly:

```python
logger.info("Running pipeline immediately on startup")
run_pipeline(config)

logger.info("Scheduler started")
scheduler.start()
```

The immediate run must complete (or raise) before the scheduler begins — it is not run in a background thread. Errors from the immediate run are already handled inside `run_pipeline` (per-file `_err.txt`), so no extra error handling is needed here.

### 2. Tests — `tests/test_scheduler.py` (or new file)

- When `start_scheduler` is called, `run_pipeline` is invoked **before** `scheduler.start()`.
- The scheduler still registers the job for subsequent runs.
- The immediate run happens for both `cron` and `interval` schedule types.

## Acceptance Criteria

- On service start (scheduler mode), the pipeline runs immediately without waiting for the first scheduled trigger.
- After the immediate run, the scheduler fires on the configured schedule as before.
- `--once` mode is unaffected (it already runs once and exits).
- `--dry-run` mode is unaffected.
- Existing scheduler tests continue to pass.

## Out of Scope

- Making the immediate run optional via a config flag.
- Running the immediate run in a background thread.
- Changing the schedule timing relative to startup (e.g. "interval starts after immediate run finishes").
