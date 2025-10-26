from __future__ import annotations

from dataclasses import dataclass
from datetime import time, timedelta

REFERENCE_KICKOFF_TIME = time.fromisoformat("19:00:00")


def _parse_time(value: str) -> time:
    hours, minutes, seconds = (int(part) for part in value.split(":", 2))
    return time(hour=hours, minute=minutes, second=seconds)


def _parse_duration(value: str) -> timedelta:
    hours, minutes, seconds = (int(part) for part in value.split(":", 2))
    return timedelta(hours=hours, minutes=minutes, seconds=seconds)


@dataclass(frozen=True)
class BroadcastPlanEntry:
    planned_time: time
    duration: timedelta
    note: str


BROADCAST_PLAN: tuple[BroadcastPlanEntry, ...] = (
    BroadcastPlanEntry(
        planned_time=_parse_time("19:30:00"),
        duration=_parse_duration("00:00:45"),
        note="Ende 1. Satz: 45 Sekunden Fazit",
    ),
    BroadcastPlanEntry(
        planned_time=_parse_time("19:30:45"),
        duration=_parse_duration("00:01:30"),
        note="01:30 Minuten ohne Kommentar",
    ),
    BroadcastPlanEntry(
        planned_time=_parse_time("19:32:15"),
        duration=_parse_duration("00:00:45"),
        note="45 Sekunden Wiedereinstieg vor dem 2. Satz",
    ),
)

__all__ = [
    "REFERENCE_KICKOFF_TIME",
    "BroadcastPlanEntry",
    "BROADCAST_PLAN",
]
