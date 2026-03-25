from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from usc_kommentatoren.report import format_mvp_rankings_section


def test_format_mvp_rankings_section_uses_all_players_top3_per_team() -> None:
    rankings = {
        "generated_at": "2026-03-25T13:02:26.824823+00:00",
        "home_team": "USC Münster",
        "opponent_team": "Dresdner SC",
        "limit": 3,
        "scan_limit": 50,
        "indicators": [
            {
                "id": "60245649",
                "label": "alle Spielelemente / Top-Scorer",
                "pages": 6,
                "all_players": [
                    {"col_0": "1.", "Name": "Other Player", "Mannschaft": "Suhl", "Top-Scorer": "278"},
                    {"col_0": "2.", "Name": "Marta Levinska", "Mannschaft": "Dresden", "Top-Scorer": "199"},
                    {"col_0": "3.", "Name": "Another Other", "Mannschaft": "Aachen", "Top-Scorer": "166"},
                    {"col_0": "5.", "Name": "Esther Spöler", "Mannschaft": "Münster", "Top-Scorer": "129"},
                    {"col_0": "7.", "Name": "Mette Marleen Pfeffer", "Mannschaft": "Dresden", "Top-Scorer": "115"},
                    {"col_0": "9.", "Name": "Second Münster", "Mannschaft": "USC Münster", "Top-Scorer": "101"},
                    {"col_0": "11.", "Name": "Third Dresden", "Mannschaft": "Dresdner SC", "Top-Scorer": "93"},
                    {"col_0": "13.", "Name": "Third Münster", "Mannschaft": "Münster", "Top-Scorer": "88"},
                    {"col_0": "15.", "Name": "Fourth Dresden", "Mannschaft": "Dresden", "Top-Scorer": "77"},
                ],
            }
        ],
    }

    html = format_mvp_rankings_section(rankings, usc_name="USC Münster", opponent_name="Dresdner SC")

    # Opponent entries are listed first, limited to top 3 within the indicator's all_players list.
    assert "Marta Levinska" in html
    assert "Mette Marleen Pfeffer" in html
    assert "Third Dresden" in html
    assert "Fourth Dresden" not in html

    # USC entries are listed second, also limited to top 3.
    assert "Esther Spöler" in html
    assert "Second Münster" in html
    assert "Third Münster" in html

    # Ensure no empty-state message is shown when all_players contains matching teams.
    assert "Keine MVP-Rankings" not in html


def test_format_mvp_rankings_section_deduplicates_identical_entries() -> None:
    rankings = {
        "generated_at": "2026-03-25T13:02:26.824823+00:00",
        "home_team": "USC Münster",
        "opponent_team": "Dresdner SC",
        "limit": 3,
        "scan_limit": 50,
        "indicators": [
            {
                "id": "dup-check",
                "label": "Aufschlag / Quote Aufschläge mit Wirkung",
                "pages": 6,
                "all_players": [
                    {
                        "col_0": "32.",
                        "Name": "Pfeffer, Mette Marleen",
                        "Mannschaft": "Dresdner SC",
                        "Quote Aufschläge mit Wirkung": "29,5%",
                        "Sätze": "70",
                        "Spiele": "20",
                    },
                    {
                        "col_0": "38.",
                        "Name": "Siksna, Amanda",
                        "Mannschaft": "Dresdner SC",
                        "Quote Aufschläge mit Wirkung": "28,6%",
                        "Sätze": "58",
                        "Spiele": "19",
                    },
                    {
                        "col_0": "32.",
                        "Name": "Pfeffer, Mette Marleen",
                        "Mannschaft": "Dresdner SC",
                        "Quote Aufschläge mit Wirkung": "29,5%",
                        "Sätze": "70",
                        "Spiele": "20",
                    },
                ],
            }
        ],
    }

    html = format_mvp_rankings_section(rankings, usc_name="USC Münster", opponent_name="Dresdner SC")

    assert html.count("Pfeffer, Mette Marleen") == 1
