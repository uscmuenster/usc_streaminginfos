"""Unit-Tests für die generische Heimspiel-Suche."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

# Sicherstellen, dass das src-Verzeichnis im Pfad liegt
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from usc_kommentatoren.report import (
    BERLIN_TZ,
    Match,
    find_next_home_match,
    find_next_usc_home_match,
    normalize_name,
)
from usc_kommentatoren.lineups import (
    ScheduleRow,
    find_last_known_home_opponent,
    find_next_home_match_row,
    find_next_usc_home_match_row,
    find_recent_matches_for_home_team,
    find_recent_usc_matches,
)


def _dt(year: int, month: int, day: int, hour: int = 18) -> datetime:
    return datetime(year, month, day, hour, 0, 0, tzinfo=BERLIN_TZ)


def _match(
    home: str,
    away: str,
    kickoff: datetime,
    *,
    result: bool = False,
) -> Match:
    return Match(
        kickoff=kickoff,
        home_team=home,
        away_team=away,
        host=home,
        location="Halle",
        result=None,
        competition="Test",
    )


def _row(
    home: str,
    away: str,
    kickoff: datetime,
    *,
    finished: bool = False,
) -> ScheduleRow:
    return ScheduleRow(
        match_number="001",
        kickoff=kickoff,
        home_team=home,
        away_team=away,
        competition="Test",
        venue="Halle",
        season="2024/25",
        result_label="3:0" if finished else "-",
        score="3:0" if finished else None,
        total_points=None,
        set_scores=(),
    )


class TestFindNextHomeMatch:
    def test_finds_home_match_for_configured_team(self) -> None:
        reference = _dt(2025, 1, 10)
        matches = [
            _match("Dresdner SC", "VC Wiesbaden", _dt(2025, 1, 20)),
            _match("USC Münster", "Dresdner SC", _dt(2025, 1, 15)),
        ]
        result = find_next_home_match(matches, "Dresdner SC", reference=reference)
        assert result is not None
        assert result.home_team == "Dresdner SC"

    def test_returns_none_if_no_future_home_game(self) -> None:
        reference = _dt(2025, 3, 1)
        matches = [
            _match("Dresdner SC", "VC Wiesbaden", _dt(2025, 1, 20)),
        ]
        result = find_next_home_match(matches, "Dresdner SC", reference=reference)
        assert result is None

    def test_finds_earliest_upcoming_home_match(self) -> None:
        reference = _dt(2025, 1, 1)
        matches = [
            _match("USC Münster", "SSC", _dt(2025, 1, 25)),
            _match("USC Münster", "DSC", _dt(2025, 1, 15)),
        ]
        result = find_next_home_match(matches, "USC Münster", reference=reference)
        assert result is not None
        assert result.away_team == "DSC"

    def test_backward_compat_usc_wrapper(self) -> None:
        reference = _dt(2025, 1, 1)
        matches = [
            _match("USC Münster", "DSC", _dt(2025, 1, 15)),
        ]
        generic = find_next_home_match(matches, "USC Münster", reference=reference)
        compat = find_next_usc_home_match(matches, reference=reference)
        assert generic == compat

    def test_does_not_return_away_match(self) -> None:
        reference = _dt(2025, 1, 1)
        matches = [
            _match("VC Wiesbaden", "USC Münster", _dt(2025, 1, 20)),
        ]
        result = find_next_home_match(matches, "USC Münster", reference=reference)
        assert result is None

    def test_different_team_does_not_match(self) -> None:
        reference = _dt(2025, 1, 1)
        matches = [
            _match("Dresdner SC", "VC Wiesbaden", _dt(2025, 1, 20)),
        ]
        result = find_next_home_match(matches, "USC Münster", reference=reference)
        assert result is None


class TestFindNextHomeMatchRow:
    def test_finds_row_for_home_team(self) -> None:
        reference = _dt(2025, 1, 10)
        rows = [
            _row("Dresdner SC", "VC Wiesbaden", _dt(2025, 1, 20)),
            _row("USC Münster", "Dresdner SC", _dt(2025, 1, 15)),
        ]
        result = find_next_home_match_row(rows, "Dresdner SC", reference=reference)
        assert result is not None
        assert result.home_team == "Dresdner SC"

    def test_backward_compat_usc_row_wrapper(self) -> None:
        reference = _dt(2025, 1, 1)
        rows = [
            _row("USC Münster", "DSC", _dt(2025, 1, 15)),
        ]
        generic = find_next_home_match_row(rows, "USC Münster", reference=reference)
        compat = find_next_usc_home_match_row(rows, reference=reference)
        assert generic == compat


class TestFindRecentMatchesForHomeTeam:
    def test_finds_recent_finished_matches(self) -> None:
        reference = _dt(2025, 2, 1)
        rows = [
            _row("Dresdner SC", "VC Wiesbaden", _dt(2025, 1, 20), finished=True),
            _row("USC Münster", "Dresdner SC", _dt(2025, 1, 15), finished=True),
            _row("Dresdner SC", "SSC", _dt(2025, 1, 10), finished=True),
        ]
        result = find_recent_matches_for_home_team(rows, "Dresdner SC", limit=2)
        assert len(result) == 2
        assert all("dresdner" in r.home_team.lower() or "dresdner" in r.away_team.lower() for r in result)

    def test_backward_compat_usc_recent_wrapper(self) -> None:
        rows = [
            _row("USC Münster", "DSC", _dt(2025, 1, 15), finished=True),
            _row("DSC", "USC Münster", _dt(2025, 1, 10), finished=True),
        ]
        generic = find_recent_matches_for_home_team(rows, "USC Münster", limit=5)
        compat = find_recent_usc_matches(rows, limit=5)
        assert generic == compat

    def test_excludes_unfinished_matches(self) -> None:
        rows = [
            _row("Dresdner SC", "VC Wiesbaden", _dt(2025, 1, 20), finished=False),
        ]
        result = find_recent_matches_for_home_team(rows, "Dresdner SC", limit=2)
        assert result == []


class TestFindLastKnownHomeOpponent:
    def test_returns_last_finished_home_opponent(self) -> None:
        reference = _dt(2025, 2, 1)
        rows = [
            _row("USC Münster", "DSC", _dt(2025, 1, 5), finished=True),
            _row("VC Wiesbaden", "USC Münster", _dt(2025, 1, 10), finished=True),
            _row("USC Münster", "SSC", _dt(2025, 1, 20), finished=True),
        ]
        result = find_last_known_home_opponent(rows, "USC Münster", reference=reference)
        assert result == "SSC"

    def test_returns_none_without_finished_home_match(self) -> None:
        reference = _dt(2025, 2, 1)
        rows = [
            _row("VC Wiesbaden", "USC Münster", _dt(2025, 1, 10), finished=True),
            _row("USC Münster", "DSC", _dt(2025, 2, 5), finished=False),
        ]
        result = find_last_known_home_opponent(rows, "USC Münster", reference=reference)
        assert result is None
