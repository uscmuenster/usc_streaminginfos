"""Tests für die Unicode-robuste Team-Code-Ermittlung in lineups.py."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from usc_kommentatoren.lineups import (
    MatchLineups,
    ScheduleRow,
    SetLineup,
    _find_team_code,
    _normalize_team_name,
)

BERLIN_TZ = ZoneInfo("Europe/Berlin")


def _dummy_match(team_names: dict) -> MatchLineups:
    row = ScheduleRow(
        match_number="001",
        kickoff=datetime(2025, 1, 15, 18, 0, tzinfo=BERLIN_TZ),
        home_team="Team A",
        away_team="Team B",
        competition="Test",
        venue="Halle",
        season="2024/25",
        result_label="3:0",
        score="3:0",
        total_points=None,
        set_scores=(),
    )
    return MatchLineups(
        match=row,
        pdf_url="",
        team_names=team_names,
        sets=[],
        rosters={},
    )


class TestNormalizeTeamName:
    def test_strips_combining_chars(self) -> None:
        # ü → u after NFKD decomposition
        assert _normalize_team_name("Münster") == _normalize_team_name("Munster")

    def test_case_insensitive(self) -> None:
        assert _normalize_team_name("Dresdner SC") == _normalize_team_name("dresdner sc")

    def test_whitespace_collapse(self) -> None:
        assert _normalize_team_name("USC  Münster") == _normalize_team_name("USC Münster")

    def test_umlaut_variants(self) -> None:
        assert _normalize_team_name("Schw.-Weiß Erfurt") != _normalize_team_name("Dresdner SC")
        assert _normalize_team_name("Schw.-Weiß Erfurt") == _normalize_team_name("Schw.-Weiss Erfurt")


class TestFindTeamCode:
    def test_exact_match(self) -> None:
        team_names = {"A": "Dresdner SC", "B": "VC Wiesbaden"}
        assert _find_team_code(team_names, "Dresdner SC") == "A"

    def test_case_insensitive(self) -> None:
        team_names = {"A": "Dresdner SC", "B": "VC Wiesbaden"}
        assert _find_team_code(team_names, "dresdner sc") == "A"

    def test_umlaut_in_pdf_name(self) -> None:
        """PDF hat 'Munster', Spielplan hat 'Münster' – soll trotzdem matchen."""
        team_names = {"A": "USC Munster", "B": "Dresdner SC"}
        assert _find_team_code(team_names, "USC Münster") == "A"

    def test_umlaut_in_target(self) -> None:
        """Spielplan hat 'Munster', gesucht wird 'Münster' – soll trotzdem matchen."""
        team_names = {"A": "USC Münster", "B": "Dresdner SC"}
        assert _find_team_code(team_names, "USC Munster") == "A"

    def test_partial_match(self) -> None:
        """PDF verwendet abgekürzten Namen ('USC'), Spielplan 'USC Münster'."""
        team_names = {"A": "USC", "B": "DSC"}
        assert _find_team_code(team_names, "USC Münster") == "A"

    def test_returns_none_for_no_match(self) -> None:
        team_names = {"A": "Dresdner SC", "B": "VC Wiesbaden"}
        assert _find_team_code(team_names, "SSC Palmberg Schwerin") is None

    def test_different_teams_not_confused(self) -> None:
        team_names = {"A": "USC Münster", "B": "Dresdner SC"}
        assert _find_team_code(team_names, "Dresdner SC") == "B"
        assert _find_team_code(team_names, "USC Münster") == "A"


class TestMatchLineupsGetHomeCode:
    def test_get_home_code_usc(self) -> None:
        ml = _dummy_match({"A": "USC Münster", "B": "Dresdner SC"})
        assert ml.get_home_code("USC Münster") == "A"

    def test_get_home_code_dresdner(self) -> None:
        ml = _dummy_match({"A": "Dresdner SC", "B": "USC Münster"})
        assert ml.get_home_code("Dresdner SC") == "A"

    def test_get_home_code_umlaut_variant(self) -> None:
        """PDF-Name ohne Umlaut soll dem Spielplan-Namen mit Umlaut entsprechen."""
        ml = _dummy_match({"A": "USC Munster", "B": "Dresdner SC"})
        assert ml.get_home_code("USC Münster") == "A"

    def test_get_opponent_code(self) -> None:
        ml = _dummy_match({"A": "USC Münster", "B": "Dresdner SC"})
        assert ml.get_opponent_code("USC Münster") == "B"

    def test_usc_code_backward_compat(self) -> None:
        """Legacy usc_code property still works for USC Münster."""
        ml = _dummy_match({"A": "USC Münster", "B": "Dresdner SC"})
        assert ml.usc_code == "A"

    def test_usc_code_returns_none_for_non_usc(self) -> None:
        """Legacy usc_code returns None when USC is not involved."""
        ml = _dummy_match({"A": "Dresdner SC", "B": "VC Wiesbaden"})
        assert ml.usc_code is None
