"""Free-tier rate limit guard.

Enforces two windows simultaneously:
- RPM: at most MAX_RPM calls in the trailing 60 seconds.
- RPD: at most MAX_RPD calls since UTC midnight.

On breach, raises RateLimitReached. The caller decides whether to sleep,
skip, or exit — we do not silently retry.
"""
from __future__ import annotations

import sqlite3
import time

from mail_pilot.db.repository import (
    calls_last_minute,
    calls_today,
    oldest_call_in_last_minute,
)


class RateLimitReached(RuntimeError):
    def __init__(self, kind: str, wait_seconds: float = 0.0):
        super().__init__(f"{kind} limit reached (wait ~{wait_seconds:.0f}s)")
        self.kind = kind
        self.wait_seconds = wait_seconds


class RateBudget:
    def __init__(self, conn: sqlite3.Connection, *,
                 max_rpm: int = 15, max_rpd: int = 500,
                 safety_margin: int = 1):
        self.conn = conn
        self.max_rpm = max_rpm - safety_margin
        self.max_rpd = max_rpd - safety_margin

    def remaining_today(self) -> int:
        return max(0, self.max_rpd - calls_today(self.conn))

    def check(self) -> None:
        if calls_today(self.conn) >= self.max_rpd:
            raise RateLimitReached("RPD", wait_seconds=3600)

    def wait_if_needed(self) -> None:
        """Sleep just long enough to stay under RPM before the next call."""
        rpm = calls_last_minute(self.conn)
        if rpm < self.max_rpm:
            return
        oldest = oldest_call_in_last_minute(self.conn)
        if not oldest:
            return
        # oldest is 'YYYY-MM-DDTHH:MM:SSZ'. Compute seconds until it ages out.
        from datetime import datetime, timezone
        try:
            t_oldest = datetime.strptime(oldest, "%Y-%m-%dT%H:%M:%SZ") \
                .replace(tzinfo=timezone.utc)
        except ValueError:
            time.sleep(5)
            return
        elapsed = (datetime.now(timezone.utc) - t_oldest).total_seconds()
        sleep_for = max(0.0, 61 - elapsed)
        if sleep_for > 0:
            time.sleep(min(sleep_for, 65))