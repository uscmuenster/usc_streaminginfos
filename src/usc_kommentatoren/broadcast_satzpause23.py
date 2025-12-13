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
        duration=_parse_duration("00:00:20"),
        note="Ende 2. Satz: 20 Sekunden Fazit",
    ),
    BroadcastPlanEntry(
        planned_time=_parse_time("19:30:20"),
        duration=_parse_duration("00:05:20"),
        note="Werbung 2 (Regie: saubere K1, Kommentatoren: still).",
    ),
    BroadcastPlanEntry(
        planned_time=_parse_time("19:35:40"),
        duration=_parse_duration("00:00:20"),
        note="20 Sekunden Wiedereinstieg vor dem 3. Satz",
    ),
    BroadcastPlanEntry(
        planned_time=_parse_time("19:36:00"),
        duration=_parse_duration("00:00:00"),
        note="Beginn 3. Satz",
    ),
)

__all__ = [
    "REFERENCE_KICKOFF_TIME",
    "BroadcastPlanEntry",
    "BROADCAST_PLAN",
]
