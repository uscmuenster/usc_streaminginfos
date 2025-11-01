from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import time, timedelta
from pathlib import Path

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


def _load_broadcast_plan_from_csv(csv_path: Path) -> tuple[BroadcastPlanEntry, ...]:
    entries: list[BroadcastPlanEntry] = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            planned_time_raw = row.get("planned_time")
            duration_raw = row.get("duration")
            note = (row.get("note") or "").strip()
            if not planned_time_raw or not duration_raw:
                continue
            entries.append(
                BroadcastPlanEntry(
                    planned_time=_parse_time(planned_time_raw),
                    duration=_parse_duration(duration_raw),
                    note=note,
                )
            )
    return tuple(entries)


_CSV_FILENAME = Path(__file__).with_suffix(".csv")
BROADCAST_PLAN: tuple[BroadcastPlanEntry, ...] = _load_broadcast_plan_from_csv(
    _CSV_FILENAME
)

__all__ = [
    "REFERENCE_KICKOFF_TIME",
    "BroadcastPlanEntry",
    "BROADCAST_PLAN",
]
