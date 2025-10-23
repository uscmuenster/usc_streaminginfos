from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass
from html import unescape
from typing import Dict, List, Mapping, Optional, Sequence

import requests
from bs4 import BeautifulSoup
from xml.etree import ElementTree

from .report import REQUEST_HEADERS, normalize_name

LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = (10, 30)

MVP_URL = (
    "https://www.volleyball-bundesliga.de/cms/home/"
    "1_bundesliga_frauen/statistik/mvp_rankings/spielerinnenranking_hauptrunde.xhtml"
)

FORM_ID = "samsCmsComponentSubViewForComponent30088103:componentForm_30088103"
TABLE_ID = f"{FORM_ID}:rankingTable"
SELECTOR_ID = f"{FORM_ID}:indicatorSelector_30088103"
SELECTOR_INPUT_ID = f"{SELECTOR_ID}_input"
DEFAULT_INDICATOR_ID = "60245649"

MVP_HEADERS: Sequence[str] = (
    "Rang",
    "",
    "Name",
    "Sätze",
    "Spiele",
    "Position",
    "Mannschaft",
    "Nation",
    "Wert1",
    "Wert2",
    "Wert3",
    "Kennzahl",
    "Wertung",
)

MVP_INDICATORS: Mapping[str, str] = OrderedDict(
    [
        ("60245649", "alle Spielelemente / Top-Scorer"),
        ("29593924", "Aufschlag / Quote Aufschläge mit Wirkung"),
        ("31385020", "Annahme / Quote perfekte oder gute Annahme"),
        ("29593922", "Aufschlag / Quote Aufschlagpunkte"),
        ("60245660", "Annahme / Annahmeeffizienz"),
        ("29593918", "Angriff / Angriffseffizienz"),
        ("29593928", "Block / Blockpunkte"),
        ("29593923", "Aufschlag / Aufschlagpunkte"),
        ("29593919", "Angriff / Quote Angriffspunkte"),
        ("29593920", "Angriff / Angriffspunkte"),
        ("60245659", "Aufschlag / Aufschlageffizienz"),
    ]
)

TEAM_RANKING_FILTERS: Mapping[str, str] = {
    normalize_name("Allianz MTV Stuttgart"): "Stuttgart",
    normalize_name("Binder Blaubären TSV Flacht"): "Flacht",
    normalize_name("Dresdner SC"): "Dresden",
    normalize_name("ETV Hamburger Volksbank Volleys"): "Hamburg",
    normalize_name("Ladies in Black Aachen"): "Aachen",
    normalize_name("Schwarz-Weiß Erfurt"): "Erfurt",
    normalize_name("Skurios Volleys Borken"): "Borken",
    normalize_name("SSC Palmberg Schwerin"): "Schwerin",
    normalize_name("USC Münster"): "Münster",
    normalize_name("VC Wiesbaden"): "Wiesbaden",
    normalize_name("VfB Suhl LOTTO Thüringen"): "Suhl",
}

FILTER_NAME_FIELD = f"{TABLE_ID}:j_idt165:filter"
FILTER_POSITION_FIELD = f"{TABLE_ID}:j_idt176:filter"
FILTER_TEAM_FIELD = f"{TABLE_ID}:j_idt179:filter"
FILTER_METRIC_FIELD = f"{TABLE_ID}:j_idt189:filter"


@dataclass
class _MVPClient:
    session: requests.Session
    viewstate: str
    indicator: str

    @classmethod
    def create(cls) -> "_MVPClient":
        session = requests.Session()
        response = session.get(
            MVP_URL, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        viewstate_input = soup.select_one("input[name='jakarta.faces.ViewState']")
        if not viewstate_input or not viewstate_input.get("value"):
            raise RuntimeError("Konnte ViewState für MVP-Rankings nicht ermitteln.")
        viewstate = viewstate_input["value"]
        return cls(session=session, viewstate=viewstate, indicator=DEFAULT_INDICATOR_ID)

    def select_indicator(self, indicator_id: str) -> None:
        if indicator_id == self.indicator:
            return
        payload = {
            "jakarta.faces.partial.ajax": "true",
            "jakarta.faces.source": SELECTOR_ID,
            "jakarta.faces.partial.execute": SELECTOR_ID,
            "jakarta.faces.partial.render": TABLE_ID,
            "jakarta.faces.behavior.event": "change",
            "jakarta.faces.partial.event": "change",
            FORM_ID: FORM_ID,
            SELECTOR_INPUT_ID: indicator_id,
            "jakarta.faces.ViewState": self.viewstate,
        }
        response = self.session.post(
            MVP_URL,
            data=payload,
            headers=REQUEST_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        _, new_viewstate = _parse_partial_response(response.text)
        if new_viewstate:
            self.viewstate = new_viewstate
        self.indicator = indicator_id

    def fetch_team_rows(self, team_filter: str, *, rows_per_page: int = 100) -> List[List[str]]:
        payload = {
            "jakarta.faces.partial.ajax": "true",
            "jakarta.faces.source": TABLE_ID,
            "jakarta.faces.partial.execute": TABLE_ID,
            "jakarta.faces.partial.render": TABLE_ID,
            "jakarta.faces.behavior.event": "filter",
            "jakarta.faces.partial.event": "filter",
            TABLE_ID: TABLE_ID,
            f"{TABLE_ID}_filtering": "true",
            f"{TABLE_ID}_encodeFeature": "true",
            f"{TABLE_ID}_first": "0",
            f"{TABLE_ID}_rows": str(rows_per_page),
            FILTER_NAME_FIELD: "",
            FILTER_POSITION_FIELD: "",
            FILTER_TEAM_FIELD: team_filter,
            FILTER_METRIC_FIELD: "",
            "jakarta.faces.ViewState": self.viewstate,
        }
        response = self.session.post(
            MVP_URL,
            data=payload,
            headers=REQUEST_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        table_html, new_viewstate = _parse_partial_response(response.text)
        if new_viewstate:
            self.viewstate = new_viewstate
        return _extract_table_rows(table_html)


def _parse_partial_response(text: str) -> tuple[str, Optional[str]]:
    table_html = ""
    new_viewstate: Optional[str] = None
    root = ElementTree.fromstring(text)
    for update in root.findall(".//update"):
        update_id = update.get("id")
        if update_id == TABLE_ID:
            table_html = update.text or ""
        elif update_id == "jakarta.faces.ViewState":
            new_viewstate = update.text or None
    return table_html, new_viewstate


def _extract_table_rows(table_html: str) -> List[List[str]]:
    if not table_html:
        return []
    content = unescape(table_html.replace("\xa0", " "))
    soup = BeautifulSoup(content, "html.parser")
    rows: List[List[str]] = []
    for row in soup.select("tr"):
        columns = [col.get_text(" ", strip=True) for col in row.select("td")]
        if columns:
            rows.append(_reorder_row(columns))
    return rows


def _reorder_row(columns: List[str]) -> List[str]:
    """Move set and game counts directly behind the name column."""

    if len(columns) < 5:
        # Nothing to reorder (e.g. placeholder rows from the website)
        return columns

    # The third- and second-last values represent the set and game counts.
    set_count = columns[-3]
    game_count = columns[-2]

    before_metrics = columns[:3]
    metric_values = columns[3:-3]
    trailing_value = columns[-1:]

    return before_metrics + [set_count, game_count] + metric_values + trailing_value


def _resolve_team_filter(team_name: str) -> Optional[str]:
    normalized = normalize_name(team_name)
    mapped = TEAM_RANKING_FILTERS.get(normalized)
    if mapped:
        return mapped
    # Fallback: try last word of team name (e.g. "Münster")
    parts = [part for part in team_name.replace("-", " ").split() if part]
    return parts[-1] if parts else None


def _ensure_row_limit(
    rows: List[List[str]], team_label: str, limit: int
) -> List[List[str]]:
    limited = rows[:limit]
    placeholder = _build_placeholder_row(team_label)
    while len(limited) < limit:
        limited.append(list(placeholder))
    return limited


def _build_placeholder_row(team_label: str) -> List[str]:
    row = ["–", ""]
    row.extend(["–"] * (len(MVP_HEADERS) - 2))
    # position 6 corresponds to Mannschaft
    row[6] = team_label
    return row


def collect_mvp_rankings(
    team_names: Sequence[str],
    *,
    limit: int = 5,
) -> Dict[str, Dict[str, List[List[str]]]]:
    if not team_names:
        return {}

    filters: List[tuple[str, str]] = []
    for name in team_names:
        team_filter = _resolve_team_filter(name)
        if not team_filter:
            LOGGER.warning("Kein Filterwert für Team '%s' gefunden", name)
            continue
        filters.append((name, team_filter))

    if not filters:
        return {}

    client = _MVPClient.create()
    data: Dict[str, Dict[str, List[List[str]]]] = OrderedDict()

    for indicator_id, label in MVP_INDICATORS.items():
        try:
            client.select_indicator(indicator_id)
        except (requests.RequestException, ElementTree.ParseError) as exc:
            LOGGER.warning(
                "MVP-Indikator '%s' konnte nicht geladen werden: %s", label, exc
            )
            data[label] = {"headers": list(MVP_HEADERS), "rows": []}
            continue

        combined_rows: List[List[str]] = []
        for name, team_filter in filters:
            try:
                rows = client.fetch_team_rows(team_filter)
            except (requests.RequestException, ElementTree.ParseError) as exc:
                LOGGER.warning(
                    "MVP-Ranking für %s (%s) fehlgeschlagen: %s",
                    name,
                    label,
                    exc,
                )
                rows = []
            combined_rows.extend(_ensure_row_limit(rows, team_filter, limit))

        data[label] = {"headers": list(MVP_HEADERS), "rows": combined_rows}

    return data
