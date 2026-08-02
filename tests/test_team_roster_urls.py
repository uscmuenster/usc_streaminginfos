"""Regression tests for the season-specific VBL roster links."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from usc_kommentatoren.report import get_team_page_url, get_team_roster_url


CURRENT_TEAM_IDS = {
    "Allianz MTV Stuttgart": "781343665",
    "Binder Blaubären TSV Flacht": "781343898",
    "Dresdner SC": "781343694",
    "ETV Hamburger Volksbank Volleys": "781343873",
    "Ladies in Black Aachen": "781343839",
    "Rote Raben Vilsbiburg": "781345412",
    "SSC Palmberg Schwerin": "781343925",
    "Schwarz-Weiß Erfurt": "781343958",
    "Skurios Volleys Borken": "781343777",
    "USC Münster": "781343629",
    "VC Wiesbaden": "781343741",
    "VfB Suhl LOTTO Thüringen": "781343809",
}


@pytest.mark.parametrize(("team_name", "team_id"), CURRENT_TEAM_IDS.items())
def test_roster_urls_use_current_team_ids(team_name: str, team_id: str) -> None:
    """The report and CSV export must target each current VBL team entry."""
    assert get_team_roster_url(team_name) == (
        "https://www.volleyball-bundesliga.de/servlet/sportsclub/"
        f"TeamMemberCsvExport?teamId={team_id}"
    )
    assert get_team_page_url(team_name) == (
        "https://www.volleyball-bundesliga.de/cms/home/1_bundesliga_frauen/"
        "teams_spielerinnen/mannschaften.xhtml?"
        f"c.teamId={team_id}&c.view=teamMain"
    )
