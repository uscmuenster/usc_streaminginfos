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
        planned_time=_parse_time("18:40:00"),
        duration=_parse_duration("00:05:00"),
        note="LIGA Grafik-Tafel: \"Die Übertragung startet in Kürze\" → Signal auf Plattform.",
    ),
    BroadcastPlanEntry(
        planned_time=_parse_time("18:45:00"),
        duration=_parse_duration("00:00:30"),
        note="Volleyball – Opening Title + DYN VBL Opener",
    ),
    BroadcastPlanEntry(
        planned_time=_parse_time("18:45:30"),
        duration=_parse_duration("00:08:30"),
        note=(
            "Beginn Kommentar; Bild-im-Bild mit K1. "
            "Spieltagsübersicht und Rückblick, Tabelle, Schiedsrichter."
        ),
    ),
    BroadcastPlanEntry(
        planned_time=_parse_time("18:54:00"),
        duration=_parse_duration("00:03:08"),
        note="Werbung 1 (Regie: saubere K1, Kommentatoren: still).",
    ),
    BroadcastPlanEntry(
        planned_time=_parse_time("18:57:08"),
        duration=_parse_duration("00:01:52"),
        note="Wiederbeginn Kommentar, Einlauf Spielerinnen",
    ),
    BroadcastPlanEntry(
        planned_time=_parse_time("18:59:00"),
        duration=_parse_duration("00:01:00"),
        note="Aufstellungen der Mannschaften",
    ),
    BroadcastPlanEntry(
        planned_time=_parse_time("19:00:00"),
        duration=_parse_duration("00:30:00"),
        note="Spielbeginn",
    ),
    BroadcastPlanEntry(
        planned_time=_parse_time("19:30:00"),
        duration=_parse_duration("00:00:45"),
        note="45 Sekunden Fazit 1. Satz",
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
    BroadcastPlanEntry(
        planned_time=_parse_time("19:33:00"),
        duration=_parse_duration("00:30:00"),
        note="Beginn 2. Satz",
    ),
    BroadcastPlanEntry(
        planned_time=_parse_time("20:00:00"),
        duration=_parse_duration("00:03:08"),
        note="Werbung 2 (Regie: saubere K1, Kommentatoren: still).",
    ),
    BroadcastPlanEntry(
        planned_time=_parse_time("20:03:08"),
        duration=_parse_duration("00:26:52"),
        note="Beginn 3. Satz",
    ),
)

__all__ = [
    "REFERENCE_KICKOFF_TIME",
    "BroadcastPlanEntry",
    "BROADCAST_PLAN",
]
