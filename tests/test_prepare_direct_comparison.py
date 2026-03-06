"""Tests für prepare_direct_comparison mit beliebigem (nicht USC) Heimteam."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from usc_kommentatoren.report import prepare_direct_comparison


def _make_payload(
    home_team_name: str = "Dresdner SC",
    opponent_name: str = "VC Wiesbaden",
    *,
    home_sets: int = 3,
    opponent_sets: int = 1,
    home_won: bool = True,
) -> dict:
    """Erzeugt ein minimales direct_comparisons-Payload für einen Testfall."""
    return {
        "team": home_team_name,
        "generated_at": "2025-01-01T00:00:00Z",
        "seasons": [
            {
                "season": "2024/25",
                "opponents": [
                    {
                        "team": opponent_name,
                        "summary": {
                            "matches_played": 1,
                            "home_wins": 1 if home_won else 0,
                            "opponent_wins": 0 if home_won else 1,
                            "home_sets_for": home_sets,
                            "opponent_sets_for": opponent_sets,
                            "home_points_for": 240,
                            "opponent_points_for": 180,
                        },
                        "matches": [
                            {
                                "match_id": "001",
                                "date": "2025-01-15",
                                "home_team": home_team_name,
                                "away_team": opponent_name,
                                "home_sets": home_sets,
                                "opponent_sets": opponent_sets,
                                "home_points": 240,
                                "opponent_points": 180,
                                "home_won": home_won,
                            }
                        ],
                    }
                ],
            }
        ],
    }


class TestPrepareDirectComparisonGenericHomeTeam:
    def test_dresdner_sc_home_team(self) -> None:
        payload = _make_payload("Dresdner SC", "VC Wiesbaden")
        result = prepare_direct_comparison(payload, "VC Wiesbaden", home_team="Dresdner SC")
        assert result is not None
        assert result.summary.home_wins == 1
        assert result.summary.opponent_wins == 0

    def test_usc_home_team_default(self) -> None:
        payload = _make_payload("USC Münster", "VC Wiesbaden")
        result = prepare_direct_comparison(payload, "VC Wiesbaden")
        assert result is not None
        assert result.summary.home_wins == 1

    def test_away_team_fallback_uses_home_team_param(self) -> None:
        """Wenn away_team im Datensatz leer ist, soll das konfigurierte home_team genutzt werden."""
        payload = {
            "team": "Dresdner SC",
            "generated_at": "2025-01-01T00:00:00Z",
            "seasons": [
                {
                    "season": "2024/25",
                    "opponents": [
                        {
                            "team": "VC Wiesbaden",
                            "summary": {
                                "matches_played": 1,
                                "home_wins": 0,
                                "opponent_wins": 1,
                                "home_sets_for": 1,
                                "opponent_sets_for": 3,
                                "home_points_for": 180,
                                "opponent_points_for": 240,
                            },
                            "matches": [
                                {
                                    "match_id": "002",
                                    "date": "2025-01-10",
                                    # home_team is VC Wiesbaden (opponent), Dresdner SC plays away
                                    "home_team": "VC Wiesbaden",
                                    "away_team": "",  # empty → should fall back to "Dresdner SC"
                                    "home_sets": 3,
                                    "opponent_sets": 1,
                                    "home_points": 240,
                                    "opponent_points": 180,
                                    "home_won": False,  # home_won=False means configured home team lost
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        result = prepare_direct_comparison(payload, "VC Wiesbaden", home_team="Dresdner SC")
        assert result is not None
        match = result.matches[0]
        # away_team should now be "Dresdner SC", not "USC Münster"
        assert match.away_team == "Dresdner SC"
        assert match.away_team != "USC Münster"

    def test_no_usc_canonical_name_as_fallback(self) -> None:
        """prepare_direct_comparison darf USC Münster nicht als hardcoded Fallback nutzen."""
        payload = {
            "team": "Schwarz-Weiß Erfurt",
            "generated_at": "2025-01-01T00:00:00Z",
            "seasons": [
                {
                    "season": "2024/25",
                    "opponents": [
                        {
                            "team": "SSC Schwerin",
                            "summary": {
                                "matches_played": 1,
                                "home_wins": 1,
                                "opponent_wins": 0,
                                "home_sets_for": 3,
                                "opponent_sets_for": 0,
                                "home_points_for": 75,
                                "opponent_points_for": 50,
                            },
                            "matches": [
                                {
                                    "match_id": "003",
                                    "date": "2025-02-01",
                                    "home_team": "Schwarz-Weiß Erfurt",
                                    "away_team": "",  # empty fallback
                                    "home_sets": 3,
                                    "opponent_sets": 0,
                                    "home_won": True,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        result = prepare_direct_comparison(
            payload, "SSC Schwerin", home_team="Schwarz-Weiß Erfurt"
        )
        assert result is not None
        match = result.matches[0]
        assert match.away_team == "Schwarz-Weiß Erfurt"
        assert "USC" not in match.away_team
        assert "Münster" not in match.away_team

    def test_returns_none_when_opponent_not_found(self) -> None:
        payload = _make_payload("Dresdner SC", "VC Wiesbaden")
        result = prepare_direct_comparison(payload, "SSC Palmberg Schwerin", home_team="Dresdner SC")
        assert result is None
