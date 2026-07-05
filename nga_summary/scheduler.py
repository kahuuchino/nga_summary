from __future__ import annotations

import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import AppConfig
from .summary import generate_summary


def run_scheduler(config: AppConfig, pages_per_forum: int = 1, use_llm: bool = True) -> None:
    timezone = ZoneInfo(config.summary.timezone)
    while True:
        next_run = _next_run_time(config.summary.daily_run_time, timezone)
        wait_seconds = max(0, int((next_run - datetime.now(timezone)).total_seconds()))
        print(f"Next run: {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}", flush=True)
        while wait_seconds > 0:
            sleep_seconds = min(wait_seconds, 60)
            time.sleep(sleep_seconds)
            wait_seconds -= sleep_seconds

        try:
            result = generate_summary(config, pages_per_forum=pages_per_forum, use_llm=use_llm)
            print(f"Summary written: {result.output_path}", flush=True)
        except Exception as exc:  # noqa: BLE001 - scheduler should keep running after transient failures.
            print(f"Scheduled run failed: {exc}", flush=True)


def _next_run_time(value: str, timezone: ZoneInfo) -> datetime:
    hour, minute = _parse_hhmm(value)
    now = datetime.now(timezone)
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def _parse_hhmm(value: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError as exc:
        raise ValueError(f"Invalid daily_run_time: {value!r}, expected HH:MM") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid daily_run_time: {value!r}, expected HH:MM")
    return hour, minute
