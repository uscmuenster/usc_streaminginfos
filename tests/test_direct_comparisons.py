"""Unit-Tests für die generische Heimteam-Konfiguration in update_direct_comparisons."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from update_direct_comparisons import (
    _normalize,
    build_dataset,
    is_home_team,
    SeasonSource,
)


class TestIsHomeTeam:
    def test_exact_match(self) -> None:
        assert is_home_team("USC Münster", "USC Münster") is True

    def test_normalized_match(self) -> None:
        """Normalisierung über Unicode-Akzente hinweg."""
        assert is_home_team("USC Munster", "USC Münster") is True

    def test_different_team(self) -> None:
        assert is_home_team("Dresdner SC", "USC Münster") is False

    def test_none_name(self) -> None:
        assert is_home_team(None, "USC Münster") is False

    def test_empty_string(self) -> None:
        assert is_home_team("", "USC Münster") is False

    def test_dresdner_sc(self) -> None:
        assert is_home_team("Dresdner SC", "Dresdner SC") is True

    def test_dresdner_sc_does_not_match_usc(self) -> None:
        assert is_home_team("USC Münster", "Dresdner SC") is False

    def test_partial_match_candidate_in_target(self) -> None:
        """Teilstring-Match: kurzer Name ist in längerem Namen enthalten."""
        assert is_home_team("SC", "Dresdner SC") is True

    def test_case_insensitive(self) -> None:
        assert is_home_team("dresdner sc", "Dresdner SC") is True


class TestBuildDatasetOutputKeys:
    """Prüft, dass build_dataset die neuen home_* Schlüssel im JSON-Output verwendet."""

    def _make_row(
        self,
        home: str,
        away: str,
        sets_home: int,
        sets_away: int,
        match_id: str = "001",
    ) -> dict:
        return {
            "#": match_id,
            "Mannschaft 1": home,
            "Mannschaft 2": away,
            "Satzpunkte": f"{sets_home}:{sets_away}",
            "Ballpunkte": None,
            "Datum und Uhrzeit": "01.01.2025, 18:00:00",
            "Spielrunde": "VBL",
            "ST": "1",
            "Austragungsort": "Münster",
        }

    def test_summary_uses_home_keys(self) -> None:
        """Summary-Objekt enthält home_wins statt usc_wins."""
        rows_iter = iter([
            self._make_row("Dresdner SC", "VC Wiesbaden", 3, 1, "001"),
        ])

        class FakeSource(SeasonSource):
            pass

        import unittest.mock as mock

        source = FakeSource(season="2025/26", urls=["http://fake/url"])
        with mock.patch(
            "update_direct_comparisons.fetch_csv_rows",
            return_value=[self._make_row("Dresdner SC", "VC Wiesbaden", 3, 1, "001")],
        ):
            dataset = build_dataset([source], home_team="Dresdner SC")

        assert dataset["team"] == "Dresdner SC"
        seasons = dataset["seasons"]
        assert len(seasons) == 1
        opponents = seasons[0]["opponents"]
        assert len(opponents) == 1
        summary = opponents[0]["summary"]

        # Neue Schlüssel vorhanden
        assert "home_wins" in summary
        assert "opponent_wins" in summary
        assert "home_sets_for" in summary
        assert "opponent_sets_for" in summary
        # Alte usc_* Schlüssel sollen NICHT mehr im Output sein
        assert "usc_wins" not in summary
        assert "usc_losses" not in summary
        assert "usc_sets_for" not in summary
        assert "usc_sets_against" not in summary

    def test_match_uses_home_keys(self) -> None:
        """Match-Objekt enthält home_sets/home_points/home_won statt usc_*."""
        import unittest.mock as mock

        source = SeasonSource(season="2025/26", urls=["http://fake/url"])
        with mock.patch(
            "update_direct_comparisons.fetch_csv_rows",
            return_value=[self._make_row("Dresdner SC", "VC Wiesbaden", 3, 0, "002")],
        ):
            dataset = build_dataset([source], home_team="Dresdner SC")

        match = dataset["seasons"][0]["opponents"][0]["matches"][0]
        assert "home_sets" in match
        assert "home_won" in match
        # Alte Schlüssel sollen nicht mehr vorkommen
        assert "usc_sets" not in match
        assert "usc_won" not in match

    def test_home_won_correct(self) -> None:
        """home_won ist True wenn home_sets > opponent_sets."""
        import unittest.mock as mock

        source = SeasonSource(season="2025/26", urls=["http://fake/url"])
        with mock.patch(
            "update_direct_comparisons.fetch_csv_rows",
            return_value=[self._make_row("Dresdner SC", "VC Wiesbaden", 3, 1, "003")],
        ):
            dataset = build_dataset([source], home_team="Dresdner SC")

        match = dataset["seasons"][0]["opponents"][0]["matches"][0]
        assert match["home_won"] is True
        assert match["home_sets"] == 3
        assert match["opponent_sets"] == 1

    def test_opponent_wins_when_away_team_is_home_configured(self) -> None:
        """Wenn das Heimteam Auswärtsteam ist, gewinnt es trotzdem korrekt gezählt."""
        import unittest.mock as mock

        source = SeasonSource(season="2025/26", urls=["http://fake/url"])
        # Dresdner SC ist hier Auswärtsteam, spielt 3:1
        with mock.patch(
            "update_direct_comparisons.fetch_csv_rows",
            return_value=[self._make_row("VC Wiesbaden", "Dresdner SC", 1, 3, "004")],
        ):
            dataset = build_dataset([source], home_team="Dresdner SC")

        seasons = dataset["seasons"]
        opponents = seasons[0]["opponents"]
        assert len(opponents) == 1
        # Gegner ist VC Wiesbaden
        assert opponents[0]["team"] == "VC Wiesbaden"
        match = opponents[0]["matches"][0]
        # home_sets sollte die Sätze von Dresdner SC sein (3), nicht VC Wiesbaden (1)
        assert match["home_sets"] == 3
        assert match["opponent_sets"] == 1
        assert match["home_won"] is True

    def test_default_home_team_usc(self) -> None:
        """Standard-Heimteam ist USC Münster."""
        import unittest.mock as mock

        source = SeasonSource(season="2025/26", urls=["http://fake/url"])
        with mock.patch(
            "update_direct_comparisons.fetch_csv_rows",
            return_value=[self._make_row("USC Münster", "VC Wiesbaden", 3, 0, "005")],
        ):
            dataset = build_dataset([source])

        assert dataset["team"] == "USC Münster"
