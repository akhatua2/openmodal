"""Schedule types for periodic function execution."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Cron:
    """Standard cron expression schedule.

    Usage: openmodal.Cron("*/5 * * * *")  # every 5 minutes
    """

    cron_string: str

    def to_k8s_schedule(self) -> str:
        return self.cron_string


@dataclass(frozen=True)
class Period:
    """Fixed-interval schedule.

    Usage: openmodal.Period(minutes=5)
           openmodal.Period(hours=1)
    """

    seconds: int = 0
    minutes: int = 0
    hours: int = 0
    days: int = 0

    def total_seconds(self) -> int:
        return self.seconds + self.minutes * 60 + self.hours * 3600 + self.days * 86400

    def to_k8s_schedule(self) -> str:
        total = self.total_seconds()
        if total <= 0:
            raise ValueError("Period must be positive")

        total_min = max(1, total // 60)

        if total_min < 60:
            return f"*/{total_min} * * * *"

        total_hours = total_min // 60
        if total_hours < 24 and total_min % 60 == 0:
            return f"0 */{total_hours} * * *"

        if total_hours >= 24:
            total_days = total_hours // 24
            return f"0 0 */{total_days} * *"

        return f"*/{total_min} * * * *"
