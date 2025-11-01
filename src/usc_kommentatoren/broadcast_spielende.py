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
        duration=_parse_duration("00:03:00"),
        note="Spielende: 45 Sekunden Fazit + 02:15 MVP-Ehrung",
    ),
    BroadcastPlanEntry(
        planned_time=_parse_time("19:33:00"),
        duration=_parse_duration("00:03:20"),
        note="Werbung 3 (Regie: saubere K1, Kommentatoren: still).",
    ),
    BroadcastPlanEntry(
        planned_time=_parse_time("19:36:20"),
        duration=_parse_duration("00:02:00"),
        note="02:00 Minuten Interview",
    ),
    BroadcastPlanEntry(
        planned_time=_parse_time("19:38:20"),
        duration=_parse_duration("00:01:00"),
        note="Ausblick auf die nächsten Gegner + Verabschiedung (evt ins Interview integriert)",
    ),
)

__all__ = [
    "REFERENCE_KICKOFF_TIME",
    "BroadcastPlanEntry",
    "BROADCAST_PLAN",
]
