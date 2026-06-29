"""Schedule-based pipeline runner using APScheduler."""
from __future__ import annotations

import logging
import signal

from apscheduler.schedulers.blocking import BlockingScheduler

from whispercrawl.config import Config
from whispercrawl.main import run_pipeline

logger = logging.getLogger(__name__)


def _parse_interval_seconds(interval: str) -> int:
    """Parse simple interval strings like '30m', '1h', '600s'."""
    unit = interval[-1].lower()
    value = int(interval[:-1])
    return {"s": value, "m": value * 60, "h": value * 3600}[unit]


def start_scheduler(config: Config) -> None:
    scheduler = BlockingScheduler()
    sched_cfg = config.schedule

    if sched_cfg.cron:
        # e.g. "0 * * * *"
        minute, hour, day, month, day_of_week = sched_cfg.cron.split()
        scheduler.add_job(
            run_pipeline,
            "cron",
            args=[config],
            minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week,
        )
    elif sched_cfg.interval:
        seconds = _parse_interval_seconds(sched_cfg.interval)
        scheduler.add_job(run_pipeline, "interval", args=[config], seconds=seconds)
    else:
        raise ValueError("No schedule configured — use --once or set schedule.cron / schedule.interval")

    def _shutdown(signum, frame):
        logger.info("Shutting down scheduler...")
        scheduler.shutdown(wait=False)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("Running pipeline immediately on startup")
    run_pipeline(config)

    logger.info("Scheduler started")
    scheduler.start()
