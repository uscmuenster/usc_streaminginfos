from __future__ import annotations

import base64
import csv
import json
import time
from dataclasses import dataclass, replace
import re
from datetime import date, datetime, timedelta
from pathlib import Path
import mimetypes
from html import escape
from io import BytesIO, StringIO
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo
from urllib.parse import parse_qs, urljoin, urlparse
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadError

import requests
from bs4 import BeautifulSoup, Tag

DEFAULT_SCHEDULE_URL = "https://www.volleyball-bundesliga.de/servlet/league/PlayingScheduleCsvExport?matchSeriesId=776311171"
SCHEDULE_PAGE_URL = (
    "https://www.volleyball-bundesliga.de/cms/home/"
    "1_bundesliga_frauen/statistik/hauptrunde/spielplan.xhtml?playingScheduleMode=full"
)
TABLE_URL = "https://www.volleyball-bundesliga.de/cms/home/1_bundesliga_frauen/statistik/hauptrunde/tabelle_hauptrunde.xhtml"
VBL_NEWS_URL = "https://www.volleyball-bundesliga.de/cms/home/1_bundesliga_frauen/news/news.xhtml"
VBL_BASE_URL = "https://www.volleyball-bundesliga.de/"
VBL_PRESS_URL = "https://www.volleyball-bundesliga.de/cms/home/1_bundesliga_frauen/news/pressespiegel.xhtml"
WECHSELBOERSE_URL = "https://www.volleyball-bundesliga.de/cms/home/1_bundesliga_frauen/teams_spielerinnen/wechselboerse.xhtml"
TEAM_PAGE_URL = "https://www.volleyball-bundesliga.de/cms/home/1_bundesliga_frauen/teams_spielerinnen/mannschaften.xhtml"
BERLIN_TZ = ZoneInfo("Europe/Berlin")
USC_CANONICAL_NAME = "USC Münster"
USC_HOMEPAGE = "https://www.usc-muenster.de/"

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; usc-kommentatoren/1.0; +https://github.com/)"
}
HTML_ACCEPT_HEADER = {"Accept": "text/html,application/xhtml+xml"}
RSS_ACCEPT_HEADER = {"Accept": "application/rss+xml,text/xml"}
NEWS_LOOKBACK_DAYS = 14
INSTAGRAM_SEARCH_URL = "https://duckduckgo.com/html/"

GERMAN_STOPWORDS = {
    "aber",
    "als",
    "am",
    "auch",
    "auf",
    "aus",
    "bei",
    "bin",
    "bis",
    "da",
    "damit",
    "dann",
    "der",
    "die",
    "das",
    "dass",
    "den",
    "des",
    "dem",
    "ein",
    "eine",
    "einen",
    "einem",
    "er",
    "es",
    "für",
    "hat",
    "haben",
    "ich",
    "im",
    "in",
    "ist",
    "mit",
    "nach",
    "nicht",
    "noch",
    "oder",
    "sein",
    "sind",
    "so",
    "und",
    "vom",
    "von",
    "vor",
    "war",
    "wie",
    "wir",
    "zu",
}

SEARCH_TRANSLATION = str.maketrans(
    {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "Ä": "ae",
        "Ö": "oe",
        "Ü": "ue",
        "ß": "ss",
    }
)


@dataclass(frozen=True)
class MatchResult:
    score: str
    total_points: Optional[str]
    sets: tuple[str, ...]

    @property
    def summary(self) -> str:
        segments: list[str] = [self.score]
        if self.total_points:
            segments.append(f"/ {self.total_points}")
        if self.sets:
            segments.append(f"({' '.join(self.sets)})")
        return " ".join(segments)


@dataclass(frozen=True)
class MVPSelection:
    medal: Optional[str]
    name: str
    team: Optional[str] = None


@dataclass(frozen=True)
class Match:
    kickoff: datetime
    home_team: str
    away_team: str
    host: str
    location: str
    result: Optional[MatchResult]
    match_number: Optional[str] = None
    match_id: Optional[str] = None
    info_url: Optional[str] = None
    stats_url: Optional[str] = None
    scoresheet_url: Optional[str] = None
    referees: Tuple[str, ...] = ()
    attendance: Optional[str] = None
    mvps: Tuple[MVPSelection, ...] = ()

    @property
    def is_finished(self) -> bool:
        return self.result is not None


@dataclass(frozen=True)
class RosterMember:
    number_label: Optional[str]
    number_value: Optional[int]
    name: str
    role: str
    is_official: bool
    height: Optional[str]
    birthdate_label: Optional[str]
    nationality: Optional[str]


    @property
    def formatted_birthdate(self) -> Optional[str]:
        parsed = self.birthdate_value
        if parsed:
            return parsed.strftime("%d.%m.%Y")
        if not self.birthdate_label:
            return None
        value = self.birthdate_label.strip()
        return value or None

    @property
    def birthdate_value(self) -> Optional[date]:
        if not self.birthdate_label:
            return None
        value = self.birthdate_label.strip()
        if not value:
            return None
        for fmt in ("%d.%m.%Y", "%d.%m.%y"):
            try:
                parsed = datetime.strptime(value, fmt)
            except ValueError:
                continue
            return parsed.date()
        return None


@dataclass(frozen=True)
class MatchStatsTotals:
    team_name: str
    header_lines: Tuple[str, ...]
    totals_line: str
    metrics: Optional["MatchStatsMetrics"] = None


@dataclass(frozen=True)
class MatchStatsMetrics:
    serves_attempts: int
    serves_errors: int
    serves_points: int
    receptions_attempts: int
    receptions_errors: int
    receptions_positive_pct: str
    receptions_perfect_pct: str
    attacks_attempts: int
    attacks_errors: int
    attacks_blocked: int
    attacks_points: int
    attacks_success_pct: str
    blocks_points: int


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    source: str
    published: Optional[datetime]
    search_text: str = ""

    @property
    def formatted_date(self) -> Optional[str]:
        if not self.published:
            return None
        return self.published.astimezone(BERLIN_TZ).strftime("%d.%m.%Y %H:%M")


@dataclass(frozen=True)
class TransferItem:
    date: Optional[datetime]
    date_label: str
    category: Optional[str]
    type_code: str
    name: str
    url: Optional[str]
    nationality: str
    info: str
    related_club: str

    @property
    def formatted_date(self) -> str:
        if self.date:
            return self.date.strftime("%d.%m.%Y")
        return self.date_label

@dataclass(frozen=True)
class KeywordSet:
    keywords: Tuple[str, ...]
    strong: Tuple[str, ...]


def simplify_text(value: str) -> str:
    simplified = value.translate(SEARCH_TRANSLATION).lower()
    simplified = re.sub(r"\s+", " ", simplified)
    return simplified.strip()


def build_keywords(*names: str) -> KeywordSet:
    keywords: set[str] = set()
    strong: set[str] = set()
    for name in names:
        simplified = simplify_text(name)
        if not simplified:
            continue
        keywords.add(simplified)
        strong.add(simplified)
        condensed = simplified.replace(" ", "")
        if condensed:
            keywords.add(condensed)
            if condensed != simplified:
                strong.add(condensed)
        tokens = [token for token in re.split(r"[^a-z0-9]+", simplified) if token]
        keywords.update(tokens)
    return KeywordSet(tuple(sorted(keywords)), tuple(sorted(strong)))


def matches_keywords(text: str, keyword_set: KeywordSet) -> bool:
    keywords = keyword_set.keywords
    strong_keywords = keyword_set.strong
    haystack = simplify_text(text)
    if not haystack or not keywords:
        return False

    phrase_keywords = [keyword for keyword in keywords if " " in keyword]
    for keyword in phrase_keywords:
        if keyword and keyword in haystack:
            return True

    hits = {keyword for keyword in keywords if keyword and keyword in haystack}
    if not hits:
        return False

    if len(hits) >= 2:
        return True

    # Accept single matches only when they correspond to the condensed team
    # name (e.g. ``uscmunster``), not generic tokens like "Volleys".
    return any(keyword in hits for keyword in strong_keywords if keyword)


def _http_get(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, str]] = None,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> requests.Response:
    last_error: Optional[Exception] = None
    merged_headers = dict(REQUEST_HEADERS)
    if headers:
        merged_headers.update(headers)
    for attempt in range(retries):
        try:
            response = requests.get(
                url,
                timeout=30,
                headers=merged_headers,
                params=params,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:  # pragma: no cover - network errors
            last_error = exc
            if attempt == retries - 1:
                raise
            backoff = delay_seconds * (2 ** attempt)
            time.sleep(backoff)
    else:  # pragma: no cover
        if last_error:
            raise last_error
        raise RuntimeError("Unbekannter Fehler beim Abrufen von Daten.")


def fetch_html(
    url: str,
    *,
    retries: int = 5,
    delay_seconds: float = 2.0,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, str]] = None,
) -> str:
    response = _http_get(
        url,
        headers={**HTML_ACCEPT_HEADER, **(headers or {})},
        params=params,
        retries=retries,
        delay_seconds=delay_seconds,
    )
    return response.text


def fetch_rss(
    url: str,
    *,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> str:
    response = _http_get(
        url,
        headers=RSS_ACCEPT_HEADER,
        retries=retries,
        delay_seconds=delay_seconds,
    )
    return response.text


DATE_PATTERN = re.compile(
    r"(?P<day>\d{1,2})\.(?P<month>\d{1,2})\.(?P<year>\d{2,4})(?:,\s*(?P<hour>\d{1,2}):(?P<minute>\d{2}))?"
)


def parse_date_label(value: str) -> Optional[datetime]:
    match = DATE_PATTERN.search(value)
    if not match:
        return None
    day = int(match.group("day"))
    month = int(match.group("month"))
    year = int(match.group("year"))
    if year < 100:
        year += 2000
    hour = int(match.group("hour")) if match.group("hour") else 0
    minute = int(match.group("minute")) if match.group("minute") else 0
    try:
        return datetime(year, month, day, hour, minute, tzinfo=BERLIN_TZ)
    except ValueError:
        return None


def _download_schedule_text(
    url: str,
    *,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> str:
    response = _http_get(
        url,
        retries=retries,
        delay_seconds=delay_seconds,
    )
    return response.text


def fetch_schedule(
    url: str = DEFAULT_SCHEDULE_URL,
    *,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> List[Match]:
    csv_text = _download_schedule_text(url, retries=retries, delay_seconds=delay_seconds)
    return parse_schedule(csv_text)


def download_schedule(
    destination: Path,
    *,
    url: str = DEFAULT_SCHEDULE_URL,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> Path:
    csv_text = _download_schedule_text(url, retries=retries, delay_seconds=delay_seconds)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(csv_text, encoding="utf-8")
    return destination


def fetch_schedule_match_metadata(
    url: str = SCHEDULE_PAGE_URL,
    *,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> Dict[str, Dict[str, Optional[str]]]:
    response = _http_get(
        url,
        retries=retries,
        delay_seconds=delay_seconds,
    )
    soup = BeautifulSoup(response.text, "html.parser")
    metadata: Dict[str, Dict[str, Optional[str]]] = {}
    current_match_id: Optional[str] = None

    rows = soup.select("table tr")
    for row in rows:
        id_cell = row.find("td", id=re.compile(r"^match_(\d+)$"))
        if id_cell and id_cell.has_attr("id"):
            match = re.search(r"match_(\d+)", id_cell["id"])
            if match:
                current_match_id = match.group(1)

        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        number_text = cells[1].get_text(strip=True)
        if not number_text or not number_text.isdigit():
            continue

        match_number = number_text
        entry = metadata.setdefault(
            match_number,
            {
                "match_id": None,
                "info_url": None,
                "stats_url": None,
                "scoresheet_url": None,
            },
        )
        if current_match_id:
            entry["match_id"] = current_match_id

        for anchor in row.select("a[href]"):
            href = anchor["href"]
            full_href = urljoin(VBL_BASE_URL, href)
            title = (anchor.get("title") or "").lower()
            if "matchdetails" in href.lower():
                entry["info_url"] = full_href
            elif "scoresheet" in href.lower():
                entry["scoresheet_url"] = full_href
            elif "statistik" in title or "uploads" in href.lower():
                entry["stats_url"] = full_href

    return metadata


def build_match_details_url(match_id: str) -> str:
    return (
        "https://www.volleyball-bundesliga.de/popup/matchSeries/matchDetails.xhtml"
        f"?matchId={match_id}&hideHistoryBackButton=true"
    )


MVP_NAME_PART = r"[A-ZÄÖÜÀ-ÖØ-Þ][A-Za-zÄÖÜÖÄÜà-öø-ÿß'`´\-]*"
MVP_PAREN_PATTERN = re.compile(
    rf"({MVP_NAME_PART}(?:\s+{MVP_NAME_PART})*)\s*\((Gold|Silber|Silver)\)",
    re.IGNORECASE,
)
MVP_COLON_PATTERN = re.compile(
    r"MVP\s*(Gold|Silber|Silver)\s*[:\-]\s*([^,;.()]+)",
    re.IGNORECASE,
)
MVP_SUFFIX_PATTERN = re.compile(
    r"(Gold|Silber|Silver)[-\s]*MVP\s*[:\-]?\s*([^,;.()]+)",
    re.IGNORECASE,
)
MVP_KEYWORD_PATTERN = re.compile(r"MVP", re.IGNORECASE)
MVP_LOWERCASE_PARTS = {
    "de",
    "da",
    "del",
    "van",
    "von",
    "der",
    "den",
    "la",
    "le",
    "di",
    "dos",
    "das",
    "du",
}


def _normalize_medal_label(label: str) -> Optional[str]:
    normalized = label.strip().lower()
    if not normalized:
        return None
    if normalized == "silver":
        normalized = "silber"
    if normalized == "gold":
        return "Gold"
    if normalized == "silber":
        return "Silber"
    return None


def _clean_mvp_name(value: str) -> Optional[str]:
    tokens = [token for token in re.split(r"\s+", value.strip()) if token]
    if not tokens:
        return None
    collected: List[str] = []
    for token in reversed(tokens):
        cleaned = token.strip(",;:-")
        if not cleaned:
            continue
        lower = cleaned.lower()
        if not collected:
            collected.append(cleaned)
            continue
        if cleaned[0].isupper() or lower in MVP_LOWERCASE_PARTS:
            collected.append(cleaned)
        else:
            break
    collected.reverse()
    if not collected:
        return None
    return " ".join(collected)


def _extract_mvp_entries_from_text(text: str) -> Dict[str, str]:
    compact = " ".join(text.split())
    if not compact or "mvp" not in compact.lower():
        return {}
    winners: Dict[str, str] = {}
    for pattern in (MVP_PAREN_PATTERN,):
        for match in pattern.finditer(compact):
            medal = _normalize_medal_label(match.group(2))
            name = _clean_mvp_name(match.group(1))
            if medal and name and medal not in winners:
                winners[medal] = name
    for pattern in (MVP_COLON_PATTERN, MVP_SUFFIX_PATTERN):
        for match in pattern.finditer(compact):
            medal = _normalize_medal_label(match.group(1))
            name = _clean_mvp_name(match.group(2))
            if medal and name and medal not in winners:
                winners[medal] = name
    return winners


def _parse_match_mvps_from_text(soup: BeautifulSoup) -> Tuple[MVPSelection, ...]:
    collected: Dict[str, str] = {}
    seen_texts: set[str] = set()
    candidates: List[str] = []

    for element in soup.select(".hint"):
        text = element.get_text(" ", strip=True)
        compact = " ".join(text.split())
        if compact and compact not in seen_texts and MVP_KEYWORD_PATTERN.search(compact):
            candidates.append(compact)
            seen_texts.add(compact)

    for node in soup.find_all(string=MVP_KEYWORD_PATTERN):
        text = str(node)
        compact = " ".join(text.split())
        if compact and compact not in seen_texts:
            candidates.append(compact)
            seen_texts.add(compact)

    for text in candidates:
        entries = _extract_mvp_entries_from_text(text)
        for medal in ("Gold", "Silber"):
            if medal in entries and medal not in collected:
                collected[medal] = entries[medal]
        for medal, name in entries.items():
            if medal not in collected:
                collected[medal] = name
        if len(collected) >= 2:
            break

    if not collected:
        return ()

    ordered: List[MVPSelection] = []
    for medal in ("Gold", "Silber"):
        name = collected.get(medal)
        if name:
            ordered.append(MVPSelection(medal=medal, name=name, team=None))
    for medal, name in collected.items():
        if medal not in {"Gold", "Silber"}:
            ordered.append(MVPSelection(medal=medal, name=name, team=None))
    return tuple(ordered)


def _parse_match_mvps_from_table(soup: BeautifulSoup) -> List[MVPSelection]:
    header = soup.select_one(
        ".samsContentBoxHeader:-soup-contains(\"Most Valuable Player\")"
    )
    if not header:
        return []
    container = header.find_next(class_="samsContentBoxContent")
    if not container:
        return []

    team_names = [
        cell.get_text(" ", strip=True)
        for cell in soup.select(".samsMatchDetailsTeamName")
        if cell.get_text(strip=True)
    ]
    teams_by_id: Dict[str, str] = {}
    if team_names:
        teams_by_id["mvpTeam1"] = team_names[0]
        if len(team_names) > 1:
            teams_by_id["mvpTeam2"] = team_names[1]

    raw_entries: List[Dict[str, Optional[str]]] = []
    for index, cell in enumerate(container.select("td")):
        block = cell.select_one(".samsOutputMvp")
        if not block:
            continue
        name_anchor = block.select_one(".samsOutputMvpPlayerName a")
        if not name_anchor:
            continue
        name = name_anchor.get_text(strip=True)
        if not name:
            continue

        medal: Optional[str] = None
        medal_image = block.select_one(".samsOutputMvpMedalImage img[src]")
        if medal_image:
            source = medal_image["src"].lower()
            if "gold" in source:
                medal = "Gold"
            elif "silber" in source or "silver" in source:
                medal = "Silber"
        if not medal:
            extracted = _extract_mvp_entries_from_text(block.get_text(" ", strip=True))
            if "Gold" in extracted:
                medal = "Gold"
            elif "Silber" in extracted:
                medal = "Silber"
            elif extracted:
                medal = next(iter(extracted.keys()))

        team: Optional[str] = None
        cell_id = cell.get("id")
        if cell_id and cell_id in teams_by_id:
            team = teams_by_id[cell_id]
        elif team_names and index < len(team_names):
            team = team_names[index]

        raw_entries.append({"medal": medal, "name": name, "team": team})

    if not raw_entries:
        return []

    used_medals = {entry["medal"] for entry in raw_entries if entry.get("medal")}
    for entry in raw_entries:
        if entry.get("medal"):
            continue
        for candidate in ("Gold", "Silber"):
            if candidate not in used_medals:
                entry["medal"] = candidate
                used_medals.add(candidate)
                break

    selections: List[MVPSelection] = []
    for entry in raw_entries:
        name = entry.get("name")
        if not name:
            continue
        medal = entry.get("medal")
        team = entry.get("team")
        team_value = team.strip() if isinstance(team, str) and team.strip() else None
        selections.append(MVPSelection(medal=medal, name=name, team=team_value))
    return selections


def _parse_match_mvps(soup: BeautifulSoup) -> Tuple[MVPSelection, ...]:
    table_entries = _parse_match_mvps_from_table(soup)
    if table_entries:
        return tuple(table_entries)
    return _parse_match_mvps_from_text(soup)


def fetch_match_details(
    match_id: str,
    *,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> Dict[str, object]:
    url = build_match_details_url(match_id)
    response = _http_get(
        url,
        retries=retries,
        delay_seconds=delay_seconds,
    )
    soup = BeautifulSoup(response.text, "html.parser")
    referees: List[str] = []
    attendance: Optional[str] = None

    for table in soup.select("table"):
        for row in table.select("tr"):
            cells = [
                cell.get_text(" ", strip=True)
                for cell in row.find_all(["th", "td"])
            ]
            if len(cells) < 2:
                continue
            label = cells[0].lower()
            value = _normalize_schedule_field(cells[1])
            if not value:
                continue
            if "schiedsrichter" in label and "linienrichter" not in label:
                referees.append(value)
            elif "zuschauer" in label:
                attendance = value

    mvps = _parse_match_mvps(soup)

    return {
        "referees": tuple(referees),
        "attendance": attendance,
        "mvps": mvps,
    }


def enrich_match(
    match: Match,
    metadata: Dict[str, Dict[str, Optional[str]]],
    detail_cache: Dict[str, Dict[str, object]],
) -> Match:
    match_number = match.match_number
    meta = metadata.get(match_number) if match_number else None

    match_id = match.match_id or (meta.get("match_id") if meta else None)
    info_url = match.info_url or (meta.get("info_url") if meta else None)
    stats_url = match.stats_url or (meta.get("stats_url") if meta else None)
    scoresheet_url = match.scoresheet_url or (meta.get("scoresheet_url") if meta else None)

    referees = tuple(match.referees) if match.referees else ()
    attendance = match.attendance
    mvps = tuple(match.mvps) if match.mvps else ()

    if match_id:
        detail = detail_cache.get(match_id)
        if detail is None:
            detail = fetch_match_details(match_id)
            detail_cache[match_id] = detail
        fetched_referees = detail.get("referees") or ()
        if fetched_referees:
            referees = tuple(fetched_referees)
        fetched_attendance = detail.get("attendance")
        if fetched_attendance:
            attendance = fetched_attendance
        fetched_mvps = detail.get("mvps") or ()
        if fetched_mvps:
            normalized: List[MVPSelection] = []
            for entry in fetched_mvps:
                if isinstance(entry, MVPSelection):
                    normalized.append(entry)
                elif isinstance(entry, (tuple, list)) and len(entry) >= 2:
                    medal = entry[0] if entry[0] is not None else None
                    name = str(entry[1])
                    team = entry[2] if len(entry) > 2 else None
                    normalized.append(
                        MVPSelection(
                            medal=str(medal) if medal not in {None, ""} else None,
                            name=name,
                            team=str(team) if team not in {None, ""} else None,
                        )
                    )
            if normalized:
                mvps = tuple(normalized)

    return replace(
        match,
        match_number=match_number,
        match_id=match_id,
        info_url=info_url,
        stats_url=stats_url,
        scoresheet_url=scoresheet_url,
        referees=referees,
        attendance=attendance,
        mvps=mvps,
    )


def enrich_matches(
    matches: Sequence[Match],
    metadata: Dict[str, Dict[str, Optional[str]]],
    detail_cache: Optional[Dict[str, Dict[str, object]]] = None,
) -> List[Match]:
    cache = detail_cache if detail_cache is not None else {}
    return [enrich_match(match, metadata, cache) for match in matches]


def _download_roster_text(
    url: str,
    *,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> str:
    response = _http_get(
        url,
        headers={"Accept": "text/csv"},
        retries=retries,
        delay_seconds=delay_seconds,
    )
    return response.content.decode("latin-1")

OFFICIAL_ROLE_PRIORITY: Tuple[str, ...] = (
    "Trainer",
    "Co-Trainer",
    "Co-Trainer (Scout)",
    "Statistiker",
    "Physiotherapeut",
    "Arzt",
)


def _official_sort_key(member: RosterMember) -> Tuple[int, str, str]:
    role = (member.role or "").strip()
    normalized = role.lower()
    order = len(OFFICIAL_ROLE_PRIORITY)
    for index, label in enumerate(OFFICIAL_ROLE_PRIORITY):
        if normalized == label.lower():
            order = index
            break
    return (order, normalized, member.name.lower())


def parse_roster(csv_text: str) -> List[RosterMember]:
    buffer = StringIO(csv_text)
    reader = csv.DictReader(buffer, delimiter=";", quotechar="\"")
    players: List[RosterMember] = []
    officials: List[RosterMember] = []
    for row in reader:
        name = (row.get("Titel Vorname Nachname") or "").strip()
        if not name:
            continue
        number_raw = (row.get("Trikot") or "").strip()
        role = (row.get("Position/Funktion Offizieller") or "").strip()
        height = (row.get("Größe") or "").strip()
        birthdate = (row.get("Geburtsdatum") or "").strip()
        nationality = (row.get("Staatsangehörigkeit") or "").strip()
        number_value: Optional[int] = None
        is_official = True
        if number_raw:
            compact = number_raw.replace(" ", "")
            if compact.isdigit():
                number_value = int(compact)
                is_official = False
        member = RosterMember(
            number_label=number_raw or None,
            number_value=number_value,
            name=name,
            role=role,
            is_official=is_official,
            height=height or None,
            birthdate_label=birthdate or None,
            nationality=nationality or None,
        )
        if member.is_official:
            officials.append(member)
        else:
            players.append(member)

    players.sort(
        key=lambda member: (
            member.number_value if member.number_value is not None else 10_000,
            member.name.lower(),
        )
    )
    officials.sort(key=_official_sort_key)
    return players + officials


def collect_team_roster(
    team_name: str,
    directory: Path,
    *,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> List[RosterMember]:
    url = get_team_roster_url(team_name)
    if not url:
        return []
    csv_text = _download_roster_text(url, retries=retries, delay_seconds=delay_seconds)
    directory.mkdir(parents=True, exist_ok=True)
    slug = slugify_team_name(team_name) or "team"
    destination = directory / f"{slug}.csv"
    destination.write_text(csv_text, encoding="utf-8")
    return parse_roster(csv_text)


def load_schedule_from_file(path: Path) -> List[Match]:
    csv_text = path.read_text(encoding="utf-8")
    return parse_schedule(csv_text)


def parse_schedule(csv_text: str) -> List[Match]:
    buffer = StringIO(csv_text)
    reader = csv.DictReader(buffer, delimiter=";", quotechar="\"")
    matches: List[Match] = []
    for row in reader:
        try:
            kickoff = parse_kickoff(row["Datum"], row["Uhrzeit"])
        except (KeyError, ValueError):
            continue

        home_team = row.get("Mannschaft 1", "").strip()
        away_team = row.get("Mannschaft 2", "").strip()
        host = row.get("Gastgeber", "").strip()
        location = row.get("Austragungsort", "").strip()
        result = build_match_result(row)
        match_number = (row.get("#") or "").strip() or None
        attendance = _normalize_schedule_field(row.get("Zuschauerzahl"))
        referee_entries = _parse_referee_field(row.get("Schiedsgericht"))

        matches.append(
            Match(
                kickoff=kickoff,
                home_team=home_team,
                away_team=away_team,
                host=host,
                location=location,
                result=result,
                match_number=match_number,
                referees=referee_entries,
                attendance=attendance,
            )
        )
    return matches


def _normalize_schedule_field(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    value = raw.strip()
    if not value or value in {"-", "–"}:
        return None
    return value


def _parse_referee_field(raw: Optional[str]) -> Tuple[str, ...]:
    value = _normalize_schedule_field(raw)
    if not value:
        return ()
    parts = [segment.strip() for segment in re.split(r"[;,/]", value) if segment.strip()]
    return tuple(parts)


def parse_kickoff(date_str: str, time_str: str) -> datetime:
    combined = f"{date_str.strip()} {time_str.strip()}"
    kickoff = datetime.strptime(combined, "%d.%m.%Y %H:%M:%S")
    return kickoff.replace(tzinfo=BERLIN_TZ)


RESULT_PATTERN = re.compile(
    r"\s*(?P<score>\d+:\d+)"
    r"(?:\s*/\s*(?P<points>\d+:\d+))?"
    r"(?:\s*\((?P<sets>[^)]+)\))?"
)


def _parse_result_text(raw: str | None) -> Optional[MatchResult]:
    if not raw:
        return None

    cleaned = raw.strip()
    if not cleaned:
        return None
    if cleaned in {"-", "–"}:
        return None

    match = RESULT_PATTERN.match(cleaned)
    if not match:
        return MatchResult(score=cleaned, total_points=None, sets=())

    score = match.group("score")
    points = match.group("points")
    sets_raw = match.group("sets")
    sets: tuple[str, ...] = ()
    if sets_raw:
        normalized = sets_raw.replace(",", " ")
        split_sets = [segment.strip() for segment in normalized.split() if segment.strip()]
        sets = tuple(split_sets)

    return MatchResult(score=score, total_points=points, sets=sets)


def build_match_result(row: Dict[str, str]) -> Optional[MatchResult]:
    fallback = _parse_result_text(row.get("Ergebnis"))

    score = (row.get("Satzpunkte") or "").strip()
    total_points = (row.get("Ballpunkte") or "").strip()

    sets_list: list[str] = []
    for index in range(1, 6):
        home_key = f"Satz {index} - Ballpunkte 1"
        away_key = f"Satz {index} - Ballpunkte 2"
        home_points = (row.get(home_key) or "").strip()
        away_points = (row.get(away_key) or "").strip()
        if home_points and away_points:
            sets_list.append(f"{home_points}:{away_points}")

    if score or total_points or sets_list:
        if not score and fallback:
            score = fallback.score
        if not total_points and fallback and fallback.total_points:
            total_points = fallback.total_points
        sets: tuple[str, ...]
        if sets_list:
            sets = tuple(sets_list)
        elif fallback:
            sets = fallback.sets
        else:
            sets = ()

        cleaned_total = total_points or None
        if score:
            return MatchResult(score=score, total_points=cleaned_total, sets=sets)
        if fallback:
            return MatchResult(score=fallback.score, total_points=cleaned_total, sets=sets)
        return None

    return fallback


def normalize_name(value: str) -> str:
    normalized = value.lower()
    normalized = normalized.replace("ü", "u").replace("mnster", "munster")
    return normalized


def slugify_team_name(value: str) -> str:
    simplified = simplify_text(value)
    slug = re.sub(r"[^a-z0-9]+", "-", simplified)
    return slug.strip("-")


def is_usc(name: str) -> bool:
    normalized = normalize_name(name)
    return "usc" in normalized and "munster" in normalized


def _build_team_homepages() -> Dict[str, str]:
    pairs = {
        "Allianz MTV Stuttgart": "https://www.stuttgarts-schoenster-sport.de/",
        "Binder Blaubären TSV Flacht": "https://binderblaubaeren.de/",
        "Dresdner SC": "https://www.dscvolley.de/",
        "ETV Hamburger Volksbank Volleys": "https://www.etv-hamburg.de/de/etv-hamburger-volksbank-volleys/",
        "Ladies in Black Aachen": "https://ladies-in-black.de/",
        "SSC Palmberg Schwerin": "https://www.schweriner-sc.com/",
        "Schwarz-Weiß Erfurt": "https://schwarz-weiss-erfurt.de/",
        "Skurios Volleys Borken": "https://www.skurios-volleys-borken.de/",
        "USC Münster": USC_HOMEPAGE,
        "VC Wiesbaden": "https://www.vc-wiesbaden.de/",
        "VfB Suhl LOTTO Thüringen": "https://volleyball-suhl.de/",
    }
    return {normalize_name(name): url for name, url in pairs.items()}


TEAM_HOMEPAGES = _build_team_homepages()


_MANUAL_STATS_TOTALS: Optional[
    Dict[str, List[Tuple[Tuple[str, ...], str, MatchStatsMetrics]]]
] = None


def _load_manual_stats_totals() -> Dict[str, List[Tuple[Tuple[str, ...], str, MatchStatsMetrics]]]:
    global _MANUAL_STATS_TOTALS
    if _MANUAL_STATS_TOTALS is not None:
        return _MANUAL_STATS_TOTALS

    data_path = Path(__file__).with_name("data") / "match_stats_totals.json"
    if not data_path.exists():
        _MANUAL_STATS_TOTALS = {}
        return _MANUAL_STATS_TOTALS

    try:
        with data_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        _MANUAL_STATS_TOTALS = {}
        return _MANUAL_STATS_TOTALS

    manual: Dict[str, List[Tuple[Tuple[str, ...], str, MatchStatsMetrics]]] = {}
    matches = payload.get("matches", []) if isinstance(payload, dict) else []
    for match_entry in matches:
        if not isinstance(match_entry, dict):
            continue
        stats_url = match_entry.get("stats_url")
        if not stats_url:
            continue
        teams_entries: List[Tuple[Tuple[str, ...], str, MatchStatsMetrics]] = []
        for team_entry in match_entry.get("teams", []) or []:
            if not isinstance(team_entry, dict):
                continue
            name = team_entry.get("name")
            if not name:
                continue
            serve = team_entry.get("serve") or {}
            reception = team_entry.get("reception") or {}
            attack = team_entry.get("attack") or {}
            block = team_entry.get("block") or {}
            try:
                metrics = MatchStatsMetrics(
                    serves_attempts=int(serve["attempts"]),
                    serves_errors=int(serve["errors"]),
                    serves_points=int(serve["points"]),
                    receptions_attempts=int(reception["attempts"]),
                    receptions_errors=int(reception["errors"]),
                    receptions_positive_pct=str(reception["positive_pct"]),
                    receptions_perfect_pct=str(reception["perfect_pct"]),
                    attacks_attempts=int(attack["attempts"]),
                    attacks_errors=int(attack["errors"]),
                    attacks_blocked=int(attack["blocked"]),
                    attacks_points=int(attack["points"]),
                    attacks_success_pct=str(attack["success_pct"]),
                    blocks_points=int(block["points"]),
                )
            except (KeyError, TypeError, ValueError):
                continue
            normalized_keys: List[str] = []
            primary_key = normalize_name(name)
            normalized_keys.append(primary_key)
            for alias in team_entry.get("aliases", []) or []:
                alias_name = str(alias).strip()
                if not alias_name:
                    continue
                normalized_alias = normalize_name(alias_name)
                if normalized_alias not in normalized_keys:
                    normalized_keys.append(normalized_alias)
            teams_entries.append((tuple(normalized_keys), name, metrics))
        if teams_entries:
            manual[stats_url] = teams_entries

    _MANUAL_STATS_TOTALS = manual
    return manual


def get_team_homepage(team_name: str) -> Optional[str]:
    return TEAM_HOMEPAGES.get(normalize_name(team_name))


def _build_team_roster_ids() -> Dict[str, str]:
    pairs = {
        "Allianz MTV Stuttgart": "776311283",
        "Binder Blaubären TSV Flacht": "776308950",
        "Dresdner SC": "776311462",
        "ETV Hamburger Volksbank Volleys": "776308974",
        "Ladies in Black Aachen": "776311428",
        "SSC Palmberg Schwerin": "776311399",
        "Schwarz-Weiß Erfurt": "776311376",
        "Skurios Volleys Borken": "776309053",
        "USC Münster": "776311313",
        "VC Wiesbaden": "776311253",
        "VfB Suhl LOTTO Thüringen": "776311348",
    }
    return {normalize_name(name): team_id for name, team_id in pairs.items()}


TEAM_ROSTER_IDS = _build_team_roster_ids()


ROSTER_EXPORT_URL = (
    "https://www.volleyball-bundesliga.de/servlet/sportsclub/TeamMemberCsvExport"
)


def get_team_roster_url(team_name: str) -> Optional[str]:
    team_id = TEAM_ROSTER_IDS.get(normalize_name(team_name))
    if not team_id:
        return None
    return f"{ROSTER_EXPORT_URL}?teamId={team_id}"


def get_team_page_url(team_name: str) -> Optional[str]:
    team_id = TEAM_ROSTER_IDS.get(normalize_name(team_name))
    if not team_id:
        return None
    return f"{TEAM_PAGE_URL}?c.teamId={team_id}&c.view=teamMain"


PHOTO_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def _iter_cached_photos(directory: Path, slug: str) -> Iterable[Path]:
    for extension in PHOTO_EXTENSIONS:
        candidate = directory / f"{slug}{extension}"
        if candidate.exists():
            yield candidate


def _encode_photo_data_uri(path: Path, *, mime_type: Optional[str] = None) -> str:
    mime = mime_type or mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def collect_team_photo(
    team_name: str,
    directory: Path,
    *,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> Optional[str]:
    slug = slugify_team_name(team_name)
    if not slug:
        return None

    directory.mkdir(parents=True, exist_ok=True)

    for cached_path in _iter_cached_photos(directory, slug):
        try:
            return _encode_photo_data_uri(cached_path)
        except OSError:
            try:
                cached_path.unlink()
            except OSError:
                pass

    page_url = get_team_page_url(team_name)
    if not page_url:
        return None

    html = fetch_html(page_url, retries=retries, delay_seconds=delay_seconds)
    soup = BeautifulSoup(html, "html.parser")
    photo_tag = None
    for img in soup.find_all("img"):
        classes = {cls.lower() for cls in (img.get("class") or [])}
        if "teamphoto" in classes:
            photo_tag = img
            break

    if not photo_tag:
        return None

    src = photo_tag.get("src") or ""
    if not src:
        return None

    photo_url = urljoin(page_url, src)
    response = _http_get(
        photo_url,
        headers={"Accept": "image/*"},
        retries=retries,
        delay_seconds=delay_seconds,
    )
    content = response.content
    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip() or None

    suffix = Path(urlparse(photo_url).path).suffix.lower()
    if suffix not in PHOTO_EXTENSIONS:
        guessed = ""
        if content_type:
            guessed = (mimetypes.guess_extension(content_type) or "").lower()
        if guessed in PHOTO_EXTENSIONS:
            suffix = guessed
        else:
            suffix = ".jpg"

    filename = f"{slug}{suffix}"
    path = directory / filename
    path.write_bytes(content)
    return _encode_photo_data_uri(path, mime_type=content_type)


def _build_team_instagram() -> Dict[str, str]:
    pairs = {
        "Allianz MTV Stuttgart": "https://www.instagram.com/allianzmtvstuttgart/",
        "Binder Blaubären TSV Flacht": "https://www.instagram.com/binderblaubaerenflacht/",
        "Dresdner SC": "https://www.instagram.com/dsc1898/",
        "ETV Hamburger Volksbank Volleys": "https://www.instagram.com/etv.hamburgervolksbank.volleys/",
        "Ladies in Black Aachen": "https://www.instagram.com/ladiesinblackaachen/",
        "SSC Palmberg Schwerin": "https://www.instagram.com/sscpalmbergschwerin/",
        "Schwarz-Weiß Erfurt": "https://www.instagram.com/schwarzweisserfurt/",
        "Skurios Volleys Borken": "https://www.instagram.com/skurios_volleys_borken/",
        "USC Münster": "https://www.instagram.com/uscmuenster/",
        "VC Wiesbaden": "https://www.instagram.com/vc_wiesbaden/",
        "VfB Suhl LOTTO Thüringen": "https://www.instagram.com/vfbsuhl_lottothueringen/",
    }
    return {normalize_name(name): url for name, url in pairs.items()}


TEAM_INSTAGRAM = _build_team_instagram()


def get_team_instagram(team_name: str) -> Optional[str]:
    return TEAM_INSTAGRAM.get(normalize_name(team_name))


def _build_team_keyword_synonyms() -> Dict[str, Sequence[str]]:
    pairs: Dict[str, Sequence[str]] = {
        "Allianz MTV Stuttgart": ("MTV Stuttgart",),
        "Binder Blaubären TSV Flacht": ("Binder Blaubären", "TSV Flacht"),
        "Dresdner SC": ("DSC Volleys",),
        "ETV Hamburger Volksbank Volleys": ("ETV Hamburg", "Hamburg Volleys"),
        "Ladies in Black Aachen": ("Ladies in Black", "Aachen Ladies"),
        "SSC Palmberg Schwerin": ("SSC Schwerin", "Palmberg Schwerin"),
        "Schwarz-Weiß Erfurt": ("Schwarz Weiss Erfurt",),
        "Skurios Volleys Borken": ("Skurios Borken",),
        "USC Münster": ("USC Muenster",),
        "VC Wiesbaden": ("VCW Wiesbaden",),
        "VfB Suhl LOTTO Thüringen": ("VfB Suhl",),
    }
    return {normalize_name(name): synonyms for name, synonyms in pairs.items()}


TEAM_KEYWORD_SYNONYMS = _build_team_keyword_synonyms()


def get_team_keywords(team_name: str) -> KeywordSet:
    synonyms = TEAM_KEYWORD_SYNONYMS.get(normalize_name(team_name), ())
    return build_keywords(team_name, *synonyms)


TEAM_SHORT_NAMES: Mapping[str, str] = {
    normalize_name("Allianz MTV Stuttgart"): "Stuttgart",
    normalize_name("Binder Blaubären TSV Flacht"): "Flacht",
    normalize_name("Dresdner SC"): "Dresden",
    normalize_name("ETV Hamburger Volksbank Volleys"): "Hamburg",
    normalize_name("Ladies in Black Aachen"): "Aachen",
    normalize_name("SSC Palmberg Schwerin"): "Schwerin",
    normalize_name("Schwarz-Weiß Erfurt"): "Erfurt",
    normalize_name("Skurios Volleys Borken"): "Borken",
    normalize_name("USC Münster"): "Münster",
    normalize_name("VC Wiesbaden"): "Wiesbaden",
    normalize_name("VfB Suhl LOTTO Thüringen"): "Suhl",
}


def _build_team_news_config() -> Dict[str, Dict[str, str]]:
    return {
        normalize_name(USC_CANONICAL_NAME): {
            "type": "rss",
            "url": "https://www.usc-muenster.de/feed/",
            "label": "Homepage USC Münster",
        },
        normalize_name("ETV Hamburger Volksbank Volleys"): {
            "type": "etv",
            "url": "https://www.etv-hamburg.de/de/etv-hamburger-volksbank-volleys/",
            "label": "Homepage ETV Hamburger Volksbank Volleys",
        },
    }


TEAM_NEWS_CONFIG = _build_team_news_config()


def _deduplicate_news(items: Sequence[NewsItem]) -> List[NewsItem]:
    seen: set[str] = set()
    deduped: List[NewsItem] = []
    for item in items:
        key = item.url.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _filter_by_keywords(items: Sequence[NewsItem], keyword_set: KeywordSet) -> List[NewsItem]:
    return [
        item
        for item in items
        if matches_keywords(item.search_text or item.title, keyword_set)
    ]


def _extract_best_candidate(soup: BeautifulSoup) -> Optional[str]:
    best_text = ""
    for element in soup.find_all(["article", "section", "div", "main"], limit=200):
        text = element.get_text(" ", strip=True)
        if len(text) > len(best_text):
            best_text = text
    if not best_text and soup.body:
        best_text = soup.body.get_text(" ", strip=True)
    return best_text or None


def extract_article_text(url: str) -> Optional[str]:
    try:
        html = fetch_html(url)
    except requests.RequestException:
        return None

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "noscript", "template"]):
        tag.decompose()

    hostname = urlparse(url).hostname or ""
    hostname = hostname.lower()

    prioritized_selectors: List[str] = []
    if "volleyball-bundesliga.de" in hostname:
        prioritized_selectors.extend(
            [
                ".samsCmsComponentContent",
                ".samsArticleBody",
                "article",
            ]
        )
    elif "usc-muenster.de" in hostname:
        prioritized_selectors.extend([
            "article",
            "div.entry-content",
        ])
    elif "etv-hamburg" in hostname:
        prioritized_selectors.extend([
            "div.article",
            "div.text-wrapper",
        ])

    for selector in prioritized_selectors:
        candidate = soup.select_one(selector)
        if candidate:
            text = candidate.get_text(" ", strip=True)
            if len(text) >= 80:
                return text

    return _extract_best_candidate(soup)


def collect_instagram_links(team_name: str, *, limit: int = 6) -> List[str]:
    links: List[str] = []
    base = get_team_instagram(team_name)
    base_slug: Optional[str] = None
    if base:
        normalized_base = base.rstrip("/")
        links.append(normalized_base)
        base_path = urlparse(normalized_base).path.strip("/")
        if base_path:
            base_slug = base_path

    query = f"{team_name} instagram"
    try:
        html = fetch_html(
            INSTAGRAM_SEARCH_URL,
            params={"q": query},
            headers={"User-Agent": REQUEST_HEADERS["User-Agent"]},
        )
    except requests.RequestException:
        return links

    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "")
        if "instagram.com" not in href:
            continue
        target = href
        if href.startswith("//"):
            parsed = urlparse("https:" + href)
            uddg = parse_qs(parsed.query).get("uddg", [""])[0]
            if uddg:
                target = uddg
        if "instagram.com" not in target:
            continue
        normalized = target.split("?")[0].rstrip("/")
        if not normalized or normalized in links:
            continue
        parsed = urlparse(normalized)
        path = parsed.path.strip("/")
        if not path:
            continue
        if base_slug:
            if path != base_slug and not path.startswith(f"{base_slug}/"):
                if not (path.startswith("p/") or path.startswith("reel/")):
                    continue
        else:
            keywords = get_team_keywords(team_name)
            if not matches_keywords(path, keywords):
                continue
        links.append(normalized)
        if len(links) >= limit:
            break

    return links


def _within_lookback(published: Optional[datetime], *, reference: datetime, lookback_days: int) -> bool:
    if not published:
        return False
    cutoff = reference - timedelta(days=lookback_days)
    return published >= cutoff


def _fetch_rss_news(
    url: str,
    *,
    label: str,
    now: datetime,
    lookback_days: int,
) -> List[NewsItem]:
    try:
        rss_text = fetch_rss(url)
    except requests.RequestException:
        return []

    try:
        root = ET.fromstring(rss_text)
    except ET.ParseError:
        return []

    items: List[NewsItem] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        pub_date_raw = item.findtext("pubDate") or ""
        if not title or not link:
            continue
        published: Optional[datetime] = None
        if pub_date_raw:
            try:
                parsed = parsedate_to_datetime(pub_date_raw)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=BERLIN_TZ)
                published = parsed.astimezone(BERLIN_TZ)
            except (TypeError, ValueError):
                published = None
        if not _within_lookback(published, reference=now, lookback_days=lookback_days):
            continue
        search_text = f"{title} {description}"
        items.append(
            NewsItem(
                title=title,
                url=link,
                source=label,
                published=published,
                search_text=search_text,
            )
        )
    return _deduplicate_news(items)


def _fetch_etv_news(
    url: str,
    *,
    label: str,
    now: datetime,
    lookback_days: int,
) -> List[NewsItem]:
    try:
        html = fetch_html(url)
    except requests.RequestException:
        return []

    soup = BeautifulSoup(html, "html.parser")
    items: List[NewsItem] = []
    seen_ids: set[str] = set()
    for block in soup.select("div[id^=news-]"):
        block_id = block.get("id") or ""
        if block_id in seen_ids:
            continue
        seen_ids.add(block_id)
        date_elem = block.select_one(".newsDate .date")
        title_elem = block.select_one(".headline2")
        if not title_elem:
            continue
        title = title_elem.get_text(strip=True)
        if not title:
            continue
        link_elem = title_elem.find("a")
        if link_elem and link_elem.has_attr("href"):
            href = link_elem["href"]
            link = urljoin(url, href)
        else:
            link = f"{url.rstrip('/') }#{block_id}"
        date_text = date_elem.get_text(strip=True) if date_elem else ""
        published = parse_date_label(date_text)
        if not _within_lookback(published, reference=now, lookback_days=lookback_days):
            continue
        summary_elem = block.select_one(".text-wrapper")
        summary = summary_elem.get_text(" ", strip=True) if summary_elem else ""
        items.append(
            NewsItem(
                title=title,
                url=link,
                source=label,
                published=published,
                search_text=f"{title} {summary}",
            )
        )
    return _deduplicate_news(items)


def _fetch_vbl_articles(
    url: str,
    *,
    label: str,
    now: datetime,
    lookback_days: int,
) -> List[NewsItem]:
    try:
        html = fetch_html(url)
    except requests.RequestException:
        return []

    soup = BeautifulSoup(html, "html.parser")
    items: List[NewsItem] = []
    for article in soup.select("div.samsArticle"):
        header_link = article.select_one(".samsArticleHeader a")
        if not header_link or not header_link.has_attr("href"):
            continue
        title = header_link.get_text(strip=True)
        if not title:
            continue
        link = urljoin(url, header_link["href"])
        info = article.select_one(".samsArticleInfo")
        date_text = info.get_text(strip=True) if info else ""
        published = parse_date_label(date_text)
        if not _within_lookback(published, reference=now, lookback_days=lookback_days):
            continue
        summary_elem = article.select_one(".samsCmsComponentContent")
        summary = summary_elem.get_text(" ", strip=True) if summary_elem else ""
        category = article.select_one(".samsArticleCategory")
        category_text = category.get_text(" ", strip=True) if category else ""
        search_text = f"{title} {summary} {category_text}"
        items.append(
            NewsItem(
                title=title,
                url=link,
                source=label,
                published=published,
                search_text=search_text,
            )
        )
    return _deduplicate_news(items)


def _fetch_vbl_press(
    url: str,
    *,
    label: str,
    now: datetime,
    lookback_days: int,
) -> List[NewsItem]:
    try:
        html = fetch_html(url)
    except requests.RequestException:
        return []

    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table.samsDataTable tbody tr")
    items: List[NewsItem] = []
    for row in rows:
        columns = row.find_all("td")
        if len(columns) < 3:
            continue
        link_elem = columns[0].find("a")
        source_elem = columns[1].get_text(strip=True)
        date_text = columns[2].get_text(strip=True)
        if not link_elem or not link_elem.has_attr("href"):
            continue
        title = link_elem.get_text(strip=True)
        if not title:
            continue
        link = link_elem["href"]
        published = parse_date_label(date_text)
        if not _within_lookback(published, reference=now, lookback_days=lookback_days):
            continue
        search_text = f"{title} {source_elem}"
        items.append(
            NewsItem(
                title=title,
                url=link,
                source=f"{source_elem} via VBL Pressespiegel",
                published=published,
                search_text=search_text,
            )
        )
    return _deduplicate_news(items)


def fetch_team_news(
    team_name: str,
    *,
    now: Optional[datetime] = None,
    lookback_days: int = NEWS_LOOKBACK_DAYS,
) -> List[NewsItem]:
    config = TEAM_NEWS_CONFIG.get(normalize_name(team_name))
    if not config:
        return []
    now = now or datetime.now(tz=BERLIN_TZ)
    label = config.get("label", team_name)
    fetch_type = config.get("type")
    url = config.get("url", "")
    if not url:
        return []
    if fetch_type == "rss":
        return _fetch_rss_news(url, label=label, now=now, lookback_days=lookback_days)
    if fetch_type == "etv":
        return _fetch_etv_news(url, label=label, now=now, lookback_days=lookback_days)
    return []


def collect_team_news(
    next_home: Match,
    *,
    now: Optional[datetime] = None,
    lookback_days: int = NEWS_LOOKBACK_DAYS,
) -> Tuple[List[NewsItem], List[NewsItem]]:
    now = now or datetime.now(tz=BERLIN_TZ)
    usc_news = fetch_team_news(USC_CANONICAL_NAME, now=now, lookback_days=lookback_days)
    opponent_news = fetch_team_news(next_home.away_team, now=now, lookback_days=lookback_days)

    vbl_articles = _fetch_vbl_articles(
        VBL_NEWS_URL,
        label="Volleyball Bundesliga",
        now=now,
        lookback_days=lookback_days,
    )
    vbl_press = _fetch_vbl_press(
        VBL_PRESS_URL,
        label="Volleyball Bundesliga",
        now=now,
        lookback_days=lookback_days,
    )

    combined_vbl = _deduplicate_news(vbl_articles + vbl_press)

    usc_keywords = get_team_keywords(USC_CANONICAL_NAME)
    opponent_keywords = get_team_keywords(next_home.away_team)

    usc_vbl = _filter_by_keywords(combined_vbl, usc_keywords)
    opponent_vbl = _filter_by_keywords(combined_vbl, opponent_keywords)

    usc_combined = _deduplicate_news([*usc_news, *usc_vbl])
    opponent_combined = _deduplicate_news([*opponent_news, *opponent_vbl])

    return usc_combined, opponent_combined


def _parse_transfer_table(table: "BeautifulSoup") -> List[TransferItem]:
    rows = table.find_all("tr")
    items: List[TransferItem] = []
    current_category: Optional[str] = None
    for row in rows:
        cells = row.find_all("td")
        if not cells:
            headers = row.find_all("th")
            if headers:
                label = headers[0].get_text(strip=True)
                if label:
                    current_category = label
            continue
        texts = [cell.get_text(strip=True) for cell in cells]
        if not any(texts):
            continue
        first = texts[0]
        parsed_date = parse_date_label(first)
        if not parsed_date and not DATE_PATTERN.match(first):
            label = first or None
            if label:
                current_category = label
            continue
        name_cell = cells[2] if len(cells) > 2 else None
        name = name_cell.get_text(strip=True) if name_cell else ""
        if not name:
            continue
        link = None
        if name_cell:
            anchor = name_cell.find("a")
            if anchor and anchor.has_attr("href"):
                link = urljoin(WECHSELBOERSE_URL, anchor["href"])
        type_code = texts[1] if len(texts) > 1 else ""
        nationality = texts[3] if len(texts) > 3 else ""
        info = texts[4] if len(texts) > 4 else ""
        related = texts[5] if len(texts) > 5 else ""
        items.append(
            TransferItem(
                date=parsed_date,
                date_label=first,
                category=current_category,
                type_code=type_code,
                name=name,
                url=link,
                nationality=nationality,
                info=info,
                related_club=related,
            )
        )
    return items


_TRANSFER_CACHE: Optional[Dict[str, List[TransferItem]]] = None


def _load_transfer_cache() -> Dict[str, List[TransferItem]]:
    global _TRANSFER_CACHE
    if _TRANSFER_CACHE is not None:
        return _TRANSFER_CACHE
    try:
        html = fetch_html(WECHSELBOERSE_URL, headers=REQUEST_HEADERS)
    except requests.RequestException:
        _TRANSFER_CACHE = {}
        return _TRANSFER_CACHE
    soup = BeautifulSoup(html, "html.parser")
    mapping: Dict[str, List[TransferItem]] = {}
    for heading in soup.find_all("h2"):
        team_name = heading.get_text(strip=True)
        if not team_name:
            continue
        collected: List[TransferItem] = []
        sibling = heading.next_sibling
        while sibling:
            if isinstance(sibling, Tag):
                if sibling.name == "h2":
                    break
                if sibling.name == "table":
                    collected.extend(_parse_transfer_table(sibling))
            sibling = sibling.next_sibling
        if collected:
            mapping[normalize_name(team_name)] = collected
    _TRANSFER_CACHE = mapping
    return mapping


def collect_team_transfers(team_name: str) -> List[TransferItem]:
    cache = _load_transfer_cache()
    return list(cache.get(normalize_name(team_name), ()))


_STATS_TOTALS_CACHE: Dict[str, Tuple[MatchStatsTotals, ...]] = {}


def _normalize_stats_header_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return ""
    if "Satz" in stripped:
        stripped = stripped[stripped.index("Satz") :]
    return re.sub(r"\s+", " ", stripped)


def _normalize_stats_totals_line(line: str) -> str:
    stripped = re.sub(r"-\s+", "-", line.strip())
    stripped = re.sub(r"\(\s*", "(", stripped)
    stripped = re.sub(r"\s*\)", ")", stripped)
    stripped = re.sub(r"\s+", " ", stripped)
    stripped = stripped.replace("%(", "% (")
    stripped = re.sub(r"%(?=\d)", "% ", stripped)
    return stripped


_MATCH_STATS_LINE_PATTERN = re.compile(
    r"(?P<serve_attempts>\d+)\s+"
    r"(?P<serve_combo>\d+)\s+"
    r"(?P<reception_attempts>\d+)\s+"
    r"(?P<reception_errors>\d+)\s+"
    r"(?P<reception_pos>\d+%)\s+\("
    r"(?P<reception_perf>\d+%)\)\s+"
    r"(?P<attack_attempts>\d+)\s+"
    r"(?P<attack_errors>\d+)\s+"
    r"(?P<attack_combo>\d+)\s+"
    r"(?P<attack_pct>\d+%)\s+"
    r"(?P<block_points>\d+)"
)


def _split_compound_value(
    value: str,
    *,
    first_max: int,
    second_max: int,
) -> Optional[Tuple[int, int]]:
    digits = re.sub(r"\D+", "", value)
    if not digits:
        return None
    max_second_len = min(3, len(digits))
    for second_len in range(1, max_second_len + 1):
        first_digits = digits[:-second_len]
        second_digits = digits[-second_len:]
        if not second_digits:
            continue
        first_value = int(first_digits) if first_digits else 0
        second_value = int(second_digits)
        if first_value <= first_max and second_value <= second_max:
            return first_value, second_value
    return None


def _parse_match_stats_metrics(line: str) -> Optional[MatchStatsMetrics]:
    match = _MATCH_STATS_LINE_PATTERN.search(line)
    if not match:
        return None
    groups = match.groupdict()
    serve_split = _split_compound_value(
        groups["serve_combo"], first_max=150, second_max=60
    )
    attack_split = _split_compound_value(
        groups["attack_combo"], first_max=60, second_max=150
    )
    if not serve_split or not attack_split:
        return None
    serves_errors, serves_points = serve_split
    attacks_blocked, attacks_points = attack_split
    try:
        return MatchStatsMetrics(
            serves_attempts=int(groups["serve_attempts"]),
            serves_errors=serves_errors,
            serves_points=serves_points,
            receptions_attempts=int(groups["reception_attempts"]),
            receptions_errors=int(groups["reception_errors"]),
            receptions_positive_pct=groups["reception_pos"],
            receptions_perfect_pct=groups["reception_perf"],
            attacks_attempts=int(groups["attack_attempts"]),
            attacks_errors=int(groups["attack_errors"]),
            attacks_blocked=attacks_blocked,
            attacks_points=attacks_points,
            attacks_success_pct=groups["attack_pct"],
            blocks_points=int(groups["block_points"]),
        )
    except ValueError:
        return None


def _extract_stats_team_names(lines: Sequence[str]) -> List[str]:
    names: List[str] = []
    team_pattern = re.compile(r"(?:Spielbericht\s+)?(.+?)\s+\d+\s*$")
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        match = team_pattern.match(stripped)
        if not match:
            continue
        candidate = match.group(1).strip()
        if not candidate or candidate.lower() == "spielbericht":
            continue
        names.append(candidate)
        if len(names) >= 2:
            break
    return names


def _parse_stats_totals_pdf(data: bytes) -> Tuple[MatchStatsTotals, ...]:
    try:
        reader = PdfReader(BytesIO(data))
    except PdfReadError:
        return ()
    except Exception:
        return ()
    if not reader.pages:
        return ()
    raw_text = reader.pages[0].extract_text() or ""
    cleaned = raw_text.replace("\x00", "")
    lines = cleaned.splitlines()
    if not lines:
        return ()
    markers = [idx for idx, line in enumerate(lines) if line.strip() == "Spieler insgesamt"]
    if not markers:
        return ()
    team_names = _extract_stats_team_names(lines)
    summaries: List[MatchStatsTotals] = []
    for marker_index, marker in enumerate(markers):
        header_lines: List[str] = []
        cursor = marker - 1
        while cursor >= 0 and len(header_lines) < 3:
            candidate = lines[cursor].strip()
            if candidate:
                header_lines.append(_normalize_stats_header_line(candidate))
            cursor -= 1
        header_lines.reverse()
        totals_line: Optional[str] = None
        for probe in range(marker + 1, len(lines)):
            candidate = lines[probe].strip()
            if not candidate:
                continue
            if candidate.startswith("Satz"):
                break
            if re.search(r"[A-Za-zÄÖÜäöüß]", candidate):
                continue
            if re.search(r"\d", candidate):
                totals_line = candidate
        if not totals_line:
            continue
        normalized_totals = _normalize_stats_totals_line(totals_line)
        team_name = team_names[marker_index] if marker_index < len(team_names) else f"Team {marker_index + 1}"
        summaries.append(
            MatchStatsTotals(
                team_name=team_name,
                header_lines=tuple(header_lines),
                totals_line=normalized_totals,
            )
        )
    return tuple(summaries)


def fetch_match_stats_totals(
    stats_url: str,
    *,
    retries: int = 3,
    delay_seconds: float = 2.0,
) -> Tuple[MatchStatsTotals, ...]:
    cached = _STATS_TOTALS_CACHE.get(stats_url)
    if cached is not None:
        return cached
    manual_entries = _load_manual_stats_totals().get(stats_url)
    try:
        response = _http_get(
            stats_url,
            retries=retries,
            delay_seconds=delay_seconds,
        )
    except requests.RequestException:
        if manual_entries:
            summaries = tuple(
                MatchStatsTotals(
                    team_name=team_name,
                    header_lines=(),
                    totals_line="",
                    metrics=metrics,
                )
                for _, team_name, metrics in manual_entries
            )
            _STATS_TOTALS_CACHE[stats_url] = summaries
            return summaries
        _STATS_TOTALS_CACHE[stats_url] = ()
        return ()
    summaries = list(_parse_stats_totals_pdf(response.content))
    if manual_entries:
        index_lookup: Dict[str, int] = {}
        for idx, (keys, _, _) in enumerate(manual_entries):
            for key in keys:
                index_lookup[key] = idx
        updated: List[MatchStatsTotals] = []
        matched_indices: set[int] = set()
        for entry in summaries:
            normalized_team = normalize_name(entry.team_name)
            match_idx = index_lookup.get(normalized_team)
            if match_idx is not None:
                matched_indices.add(match_idx)
                _, _, metrics = manual_entries[match_idx]
                updated.append(
                    MatchStatsTotals(
                        team_name=entry.team_name,
                        header_lines=entry.header_lines,
                        totals_line=entry.totals_line,
                        metrics=metrics,
                    )
                )
            else:
                updated.append(entry)
        for idx, (_keys, team_name, metrics) in enumerate(manual_entries):
            if idx in matched_indices:
                continue
            updated.append(
                MatchStatsTotals(
                    team_name=team_name,
                    header_lines=(),
                    totals_line="",
                    metrics=metrics,
                )
            )
        summaries = updated
    summaries_tuple = tuple(summaries)
    _STATS_TOTALS_CACHE[stats_url] = summaries_tuple
    return summaries_tuple


def collect_match_stats_totals(
    matches: Iterable[Match],
) -> Dict[str, Tuple[MatchStatsTotals, ...]]:
    collected: Dict[str, Tuple[MatchStatsTotals, ...]] = {}
    for match in matches:
        if not match.is_finished or not match.stats_url:
            continue
        stats_url = match.stats_url
        if stats_url in collected:
            continue
        summaries = fetch_match_stats_totals(stats_url)
        if summaries:
            collected[stats_url] = summaries
    return collected


def pretty_name(name: str) -> str:
    if is_usc(name):
        return USC_CANONICAL_NAME
    return (
        name.replace("Mnster", "Münster")
        .replace("Munster", "Münster")
        .replace("Thringen", "Thüringen")
        .replace("Wei", "Weiß")
        .replace("wei", "weiß")
    )


def get_team_short_label(name: str) -> str:
    normalized = normalize_name(name)
    short = TEAM_SHORT_NAMES.get(normalized)
    if short:
        return short
    return pretty_name(name)


def find_next_usc_home_match(matches: Iterable[Match], *, reference: Optional[datetime] = None) -> Optional[Match]:
    now = reference or datetime.now(tz=BERLIN_TZ)
    future_home_games = [
        match
        for match in matches
        if is_usc(match.host) and match.kickoff >= now
    ]
    future_home_games.sort(key=lambda match: match.kickoff)
    return future_home_games[0] if future_home_games else None


def find_last_matches_for_team(
    matches: Iterable[Match],
    team_name: str,
    *,
    limit: int,
    reference: Optional[datetime] = None,
) -> List[Match]:
    now = reference or datetime.now(tz=BERLIN_TZ)
    relevant = [
        match
        for match in matches
        if match.is_finished and match.kickoff < now and team_in_match(team_name, match)
    ]
    relevant.sort(key=lambda match: match.kickoff, reverse=True)
    return relevant[:limit]


def find_next_match_for_team(
    matches: Iterable[Match],
    team_name: str,
    *,
    reference: Optional[datetime] = None,
) -> Optional[Match]:
    now = reference or datetime.now(tz=BERLIN_TZ)
    upcoming = [
        match
        for match in matches
        if match.kickoff >= now and team_in_match(team_name, match)
    ]
    upcoming.sort(key=lambda match: match.kickoff)
    return upcoming[0] if upcoming else None


def team_in_match(team_name: str, match: Match) -> bool:
    return is_same_team(team_name, match.home_team) or is_same_team(team_name, match.away_team)


def is_same_team(a: str, b: str) -> bool:
    return normalize_name(a) == normalize_name(b)


GERMAN_WEEKDAYS = {
    0: "Mo",
    1: "Di",
    2: "Mi",
    3: "Do",
    4: "Fr",
    5: "Sa",
    6: "So",
}

GERMAN_WEEKDAYS_LONG = {
    0: "Montag",
    1: "Dienstag",
    2: "Mittwoch",
    3: "Donnerstag",
    4: "Freitag",
    5: "Samstag",
    6: "Sonntag",
}

GERMAN_MONTHS = {
    1: "Januar",
    2: "Februar",
    3: "März",
    4: "April",
    5: "Mai",
    6: "Juni",
    7: "Juli",
    8: "August",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Dezember",
}


def format_generation_timestamp(value: datetime) -> str:
    localized = value.astimezone(BERLIN_TZ)
    weekday = GERMAN_WEEKDAYS_LONG.get(localized.weekday(), localized.strftime("%A"))
    month = GERMAN_MONTHS.get(localized.month, localized.strftime("%B"))
    day = localized.day
    time_label = localized.strftime("%H:%M")
    return f"{weekday}, {day:02d}. {month} {localized.year} um {time_label}"


def format_match_line(
    match: Match,
    *,
    stats: Optional[Sequence[MatchStatsTotals]] = None,
) -> str:
    kickoff_local = match.kickoff.astimezone(BERLIN_TZ)
    date_label = kickoff_local.strftime("%d.%m.%Y")
    weekday = GERMAN_WEEKDAYS.get(kickoff_local.weekday(), kickoff_local.strftime("%a"))
    time_label = kickoff_local.strftime("%H:%M")
    kickoff_label = f"{date_label} ({weekday}) {time_label} Uhr"
    home = pretty_name(match.home_team)
    away = pretty_name(match.away_team)
    result = match.result.summary if match.result else "-"
    teams = f"{home} vs. {away}"
    result_block = ""
    if match.is_finished:
        result_block = f"<div class=\"match-result\">Ergebnis: {escape(result)}</div>"
    extras: List[str] = []
    if match.referees and not match.is_finished:
        referee_label = ", ".join(escape(referee) for referee in match.referees)
        extras.append(f"<span>Schiedsrichter: {referee_label}</span>")
    if match.attendance and match.is_finished:
        extras.append(f"<span>Zuschauer: {escape(match.attendance)}</span>")
    if match.mvps and match.is_finished:
        mvp_labels: List[str] = []
        for selection in match.mvps:
            name = selection.name.strip() if selection.name else ""
            if not name:
                continue
            raw_team = (
                selection.team.strip()
                if isinstance(selection.team, str)
                else ""
            )
            team_label = pretty_name(raw_team) if raw_team else None
            if team_label:
                mvp_labels.append(f"{escape(name)} ({escape(team_label)})")
            elif selection.medal:
                mvp_labels.append(f"{escape(selection.medal)} – {escape(name)}")
            else:
                mvp_labels.append(escape(name))
        if mvp_labels:
            if len(mvp_labels) == 2:
                rendered_mvp = " und ".join(mvp_labels)
            else:
                rendered_mvp = " / ".join(mvp_labels)
            extras.append(f"<span>MVP: {rendered_mvp}</span>")

    links: List[str] = []
    if match.info_url:
        links.append(f"<a href=\"{escape(match.info_url)}\" target=\"_blank\" rel=\"noopener\">Spielinfos</a>")
    if match.stats_url and match.is_finished:
        links.append(f"<a href=\"{escape(match.stats_url)}\" target=\"_blank\" rel=\"noopener\">Statistik (PDF)</a>")

    meta_html = ""
    if extras or links:
        combined = extras + links
        meta_html = f"<div class=\"match-meta\">{' · '.join(combined)}</div>"
    stats_html = ""
    if stats:
        normalized_home = normalize_name(match.home_team)
        normalized_away = normalize_name(match.away_team)
        normalized_usc = normalize_name(USC_CANONICAL_NAME)
        fallback_cards: List[str] = []
        table_entries: List[Tuple[str, Optional[str], MatchStatsMetrics]] = []
        tables_available = True
        for entry in stats:
            team_label = get_team_short_label(entry.team_name)
            normalized_team = normalize_name(entry.team_name)
            team_role: Optional[str] = None
            if normalized_team == normalized_usc:
                team_role = "usc"
            elif normalized_team == normalized_home:
                team_role = "home"
            elif normalized_team == normalized_away:
                team_role = "away"
            metrics = entry.metrics or _parse_match_stats_metrics(entry.totals_line)
            if metrics is None:
                tables_available = False
            else:
                table_entries.append((team_label, team_role, metrics))
            content_lines = [line for line in entry.header_lines if line]
            content_lines.append(entry.totals_line)
            content_text = "\n".join(content_lines)
            attrs: List[str] = ["class=\"match-stats-card\""]
            if team_role:
                attrs.append(f"data-team-role=\"{team_role}\"")
            attr_text = " ".join(attrs)
            card_lines = [
                f"        <article {attr_text}>",
                f"          <h4>{escape(team_label)}</h4>",
                f"          <pre>{escape(content_text)}</pre>",
                "        </article>",
            ]
            fallback_cards.append("\n".join(card_lines))
        if tables_available and table_entries:
            serve_rows: List[str] = []
            attack_rows: List[str] = []
            for team_label, team_role, metrics in table_entries:
                row_attr = f" data-team-role=\"{team_role}\"" if team_role else ""
                serve_rows.append(
                    "\n".join(
                        [
                            f"              <tr{row_attr}>",
                            f"                <th scope=\"row\">{escape(team_label)}</th>",
                            f"                <td>{metrics.serves_attempts}</td>",
                            f"                <td>{metrics.serves_errors}</td>",
                            f"                <td>{metrics.serves_points}</td>",
                            f"                <td>{metrics.receptions_attempts}</td>",
                            f"                <td>{metrics.receptions_errors}</td>",
                            f"                <td>{escape(metrics.receptions_positive_pct)} ({escape(metrics.receptions_perfect_pct)})</td>",
                            "              </tr>",
                        ]
                    )
                )
                attack_rows.append(
                    "\n".join(
                        [
                            f"              <tr{row_attr}>",
                            f"                <th scope=\"row\">{escape(team_label)}</th>",
                            f"                <td>{metrics.attacks_attempts}</td>",
                            f"                <td>{metrics.attacks_errors}</td>",
                            f"                <td>{metrics.attacks_blocked}</td>",
                            f"                <td>{metrics.attacks_points}</td>",
                            f"                <td>{escape(metrics.attacks_success_pct)}</td>",
                            f"                <td>{metrics.blocks_points}</td>",
                            "              </tr>",
                        ]
                    )
                )
            serve_rows_html = "\n".join(serve_rows)
            attack_rows_html = "\n".join(attack_rows)
            stats_html = (
                "    <details class=\"match-stats\">\n"
                "      <summary>Teamstatistik</summary>\n"
                "      <div class=\"match-stats-content\">\n"
                "        <div class=\"match-stats-table-wrapper\">\n"
                "          <table class=\"match-stats-table\">\n"
                "            <thead>\n"
                "              <tr>\n"
                "                <th scope=\"col\" rowspan=\"2\">Team</th>\n"
                "                <th scope=\"colgroup\" colspan=\"3\">Aufschlag</th>\n"
                "                <th scope=\"colgroup\" colspan=\"3\">Annahme</th>\n"
                "              </tr>\n"
                "              <tr>\n"
                "                <th scope=\"col\">Ges.</th>\n"
                "                <th scope=\"col\">Fhl</th>\n"
                "                <th scope=\"col\">Pkt</th>\n"
                "                <th scope=\"col\">Ges.</th>\n"
                "                <th scope=\"col\">Fhl</th>\n"
                "                <th scope=\"col\">Pos (Prf)</th>\n"
                "              </tr>\n"
                "            </thead>\n"
                "            <tbody>\n"
                f"{serve_rows_html}\n"
                "            </tbody>\n"
                "          </table>\n"
                "        </div>\n"
                "        <div class=\"match-stats-table-wrapper\">\n"
                "          <table class=\"match-stats-table\">\n"
                "            <thead>\n"
                "              <tr>\n"
                "                <th scope=\"col\" rowspan=\"2\">Team</th>\n"
                "                <th scope=\"colgroup\" colspan=\"5\">Angriff</th>\n"
                "                <th scope=\"colgroup\" colspan=\"1\">Block</th>\n"
                "              </tr>\n"
                "              <tr>\n"
                "                <th scope=\"col\">Ges.</th>\n"
                "                <th scope=\"col\">Fhl</th>\n"
                "                <th scope=\"col\">Blo</th>\n"
                "                <th scope=\"col\">Pkt</th>\n"
                "                <th scope=\"col\">Pkt%</th>\n"
                "                <th scope=\"col\">Pkt</th>\n"
                "              </tr>\n"
                "            </thead>\n"
                "            <tbody>\n"
                f"{attack_rows_html}\n"
                "            </tbody>\n"
                "          </table>\n"
                "        </div>\n"
                "      </div>\n"
                "    </details>"
            )
        elif fallback_cards:
            cards_html = "\n".join(fallback_cards)
            stats_html = (
                "    <details class=\"match-stats\">\n"
                "      <summary>Teamstatistik</summary>\n"
                "      <div class=\"match-stats-content\">\n"
                f"{cards_html}\n"
                "      </div>\n"
                "    </details>"
            )

    segments: List[str] = [
        "<li>",
        "  <div class=\"match-line\">",
        f"    <div class=\"match-header\"><strong>{escape(kickoff_label)}</strong> – {escape(teams)}</div>",
    ]
    if result_block:
        segments.append(f"    {result_block}")
    if meta_html:
        segments.append(f"    {meta_html}")
    if stats_html:
        segments.append(stats_html)
    segments.extend(["  </div>", "</li>"])
    return "\n".join(segments)


def format_news_list(items: Sequence[NewsItem]) -> str:
    if not items:
        return "<li>Keine aktuellen Artikel gefunden.</li>"

    rendered: List[str] = []
    for item in items:
        title = escape(item.title)
        url = escape(item.url)
        meta_parts: List[str] = [escape(item.source)] if item.source else []
        date_label = item.formatted_date
        if date_label:
            meta_parts.append(escape(date_label))
        meta = " – ".join(meta_parts)
        meta_html = f"<span class=\"news-meta\">{meta}</span>" if meta else ""
        rendered.append(
            f"<li><a href=\"{url}\">{title}</a>{meta_html}</li>"
        )
    return "\n      ".join(rendered)


MVP_DISPLAY_COLUMNS: Sequence[Tuple[str, str]] = (
    ("Rang", "Rang"),
    ("Name", "Name"),
    ("Position", "Position"),
    ("Mannschaft", "Team"),
    ("Kennzahl", "Kennzahl"),
    ("Spiele", "Spiele/Quote"),
    ("Wertung", "Wertung"),
)


def format_instagram_list(links: Sequence[str]) -> str:
    if not links:
        return "<li>Keine Links gefunden.</li>"

    rendered: List[str] = []
    for link in links:
        parsed = urlparse(link)
        segments = [segment for segment in parsed.path.split("/") if segment]
        display: str
        if not segments:
            display = f"@{parsed.netloc}" if parsed.netloc else link
        elif "p" in segments:
            index = segments.index("p")
            if index + 1 < len(segments):
                display = f"Beitrag {segments[index + 1]}"
            else:
                display = "Instagram-Post"
        elif "reel" in segments:
            index = segments.index("reel")
            if index + 1 < len(segments):
                display = f"Reel {segments[index + 1]}"
            else:
                display = "Reels"
        elif segments[0] == "stories" and len(segments) > 1:
            display = f"Stories @{segments[1]}"
        elif segments[-1] == "reels":
            display = "Reels-Übersicht"
        else:
            display = f"@{segments[0]}"
        rendered.append(f"<li><a href=\"{escape(link)}\">{escape(display)}</a></li>")
    return "\n          ".join(rendered)


def format_mvp_rankings_section(
    rankings: Optional[Mapping[str, Mapping[str, Any]]],
    *,
    usc_name: str,
    opponent_name: str,
) -> str:
    if not rankings:
        return ""

    normalized_usc = normalize_name(usc_name)
    normalized_opponent = normalize_name(opponent_name)

    def matches_team(team_normalized: str, target_normalized: str) -> bool:
        if not team_normalized or not target_normalized:
            return False
        if team_normalized == target_normalized:
            return True
        return team_normalized in target_normalized or target_normalized in team_normalized

    categories: List[str] = []
    for index, (indicator, payload) in enumerate(rankings.items()):
        headers = list((payload or {}).get("headers") or [])
        rows = list((payload or {}).get("rows") or [])
        header_index = {header: idx for idx, header in enumerate(headers)}

        team_entries: Dict[str, List[Dict[str, str]]] = {"opponent": [], "usc": []}
        for row in rows:
            values: Dict[str, str] = {}
            for header, idx in header_index.items():
                if idx < len(row):
                    values[header] = row[idx]

            name_value = escape((values.get("Name") or "").strip() or "–")
            rank_value = escape((values.get("Rang") or "").strip() or "–")
            team_raw = (values.get("Mannschaft") or values.get("Team") or "").strip()
            team_label = get_team_short_label(team_raw) if team_raw else ""
            position_raw = (values.get("Position") or "").strip()
            games_raw = (values.get("Spiele") or "").strip()
            metric_raw = (values.get("Wertung") or values.get("Kennzahl") or "").strip()
            score_value = escape(metric_raw or "–")

            if team_raw:
                normalized_team = normalize_name(team_raw)
            else:
                normalized_team = ""

            if matches_team(normalized_team, normalized_opponent):
                team_role = "opponent"
            elif matches_team(normalized_team, normalized_usc):
                team_role = "usc"
            else:
                continue

            meta_parts: List[str] = []
            if position_raw:
                meta_parts.append(escape(position_raw))
            if team_label:
                meta_parts.append(escape(team_label))
            if games_raw:
                meta_parts.append(escape(games_raw))
            meta_text = " • ".join(meta_parts)

            entry: Dict[str, str] = {
                "rank": rank_value,
                "name": name_value,
                "meta": meta_text,
                "score": score_value,
                "team": team_role,
            }
            team_entries[team_role].append(entry)

        ordered_entries: List[Dict[str, str]] = []
        for team_key in ("opponent", "usc"):
            ordered_entries.extend(team_entries[team_key][:3])

        list_items: List[str] = []
        for entry in ordered_entries:
            meta_html = (
                f"                    <span class=\"mvp-entry-meta\">{entry['meta']}</span>\n"
                if entry["meta"]
                else ""
            )
            list_items.append(
                "                <li class=\"mvp-entry\" "
                f"data-team=\"{entry['team']}\">\n"
                f"                  <span class=\"mvp-entry-rank\">{entry['rank']}</span>\n"
                "                  <div class=\"mvp-entry-info\">\n"
                f"                    <span class=\"mvp-entry-name\">{entry['name']}</span>\n"
                f"{meta_html}"
                "                  </div>\n"
                f"                  <span class=\"mvp-entry-score\">{entry['score']}</span>\n"
                "                </li>"
            )

        if list_items:
            items_html = "\n".join(list_items)
            category_body = (
                "            <div class=\"mvp-category-content\">\n"
                "              <ol class=\"mvp-list\">\n"
                f"{items_html}\n"
                "              </ol>\n"
                "            </div>\n"
            )
        else:
            category_body = (
                "            <div class=\"mvp-category-content\">\n"
                "              <p class=\"mvp-empty\">Keine MVP-Rankings für diese Kategorie verfügbar.</p>\n"
                "            </div>\n"
            )

        open_attr = " open" if index == 0 else ""
        categories.append(
            f"          <details class=\"mvp-category\"{open_attr}>\n"
            "            <summary>\n"
            f"              <span class=\"mvp-category-title\">{escape(indicator)}</span>\n"
            "              <span class=\"mvp-category-badge\">Top 3 je Team</span>\n"
            "            </summary>\n"
            f"{category_body}"
            "          </details>"
        )

    if not categories:
        return ""

    categories_html = "\n".join(categories)
    usc_label = get_team_short_label(usc_name)
    opponent_label = get_team_short_label(opponent_name)
    return (
        "\n"
        "    <section class=\"mvp-group\">\n"
        "      <details class=\"mvp-overview\">\n"
        "        <summary>MVP-Rankings</summary>\n"
        "        <div class=\"mvp-overview-content\">\n"
        "          <p class=\"mvp-note\">Top-3-Platzierungen je Team aus dem offiziellen MVP-Ranking der Volleyball Bundesliga.</p>\n"
        "          <div class=\"mvp-legend\">\n"
        f"            <span class=\"mvp-legend-item\" data-team=\"usc\">{escape(usc_label)}</span>\n"
        f"            <span class=\"mvp-legend-item\" data-team=\"opponent\">{escape(opponent_label)}</span>\n"
        "          </div>\n"
        f"{categories_html}\n"
        "        </div>\n"
        "      </details>\n"
        "    </section>\n"
        "\n"
    )


def calculate_age(birthdate: date, reference: date) -> Optional[int]:
    if birthdate > reference:
        return None
    years = reference.year - birthdate.year
    if (reference.month, reference.day) < (birthdate.month, birthdate.day):
        years -= 1
    return years


def format_roster_list(
    roster: Sequence[RosterMember], *, match_date: Optional[date] = None
) -> str:
    if not roster:
        return "<li>Keine Kaderdaten gefunden.</li>"

    rendered: List[str] = []
    if isinstance(match_date, datetime):
        match_day: Optional[date] = match_date.date()
    else:
        match_day = match_date

    for member in roster:
        number = member.number_label
        if number and number.strip().isdigit():
            number_display = f"#{number.strip()}"
        elif number:
            number_display = number.strip()
        else:
            number_display = "Staff"
        name_html = escape(member.name)
        height_display: Optional[str] = None
        if member.height and not member.is_official:
            height_value = member.height.strip()
            if height_value:
                normalized = height_value.replace(',', '.').replace(' ', '')
                if normalized.replace('.', '', 1).isdigit():
                    if not height_value.endswith('cm'):
                        height_display = f"{height_value} cm"
                    else:
                        height_display = height_value
                else:
                    height_display = height_value
        birth_display = member.formatted_birthdate
        birthdate_value = member.birthdate_value
        age_display: Optional[str] = None
        if birthdate_value and match_day:
            age_value = calculate_age(birthdate_value, match_day)
            if age_value is not None:
                age_display = f"{age_value}"
        if birth_display:
            if age_display:
                birth_display = f"{birth_display} ({age_display})"
        else:
            birth_display = "–"

        nationality_value = (member.nationality or "").strip() or "–"
        role_value = (member.role or "").strip() or "–"

        detail_parts: List[str] = []
        if not member.is_official:
            detail_parts.append(height_display or "–")
        detail_parts.append(birth_display)
        detail_parts.append(nationality_value)
        detail_parts.append(role_value)

        meta_block = "<div class=\"roster-details\">{}</div>".format(
            " | ".join(escape(part) for part in detail_parts)
        )
        classes = ["roster-item"]
        classes.append("roster-official" if member.is_official else "roster-player")
        rendered.append(
            ("<li class=\"{classes}\">"
             "<span class=\"roster-number\">{number}</span>"
             "<div class=\"roster-text\"><span class=\"roster-name\">{name}</span>{meta}</div>"
             "</li>").format(
                classes=" ".join(classes),
                number=escape(number_display),
                name=name_html,
                meta=meta_block,
            )
        )
    return "\n          ".join(rendered)


def collect_birthday_notes(
    match_date: date,
    rosters: Sequence[tuple[str, Sequence[RosterMember]]],
) -> List[str]:
    notes: List[tuple[int, str]] = []
    for _team_name, roster in rosters:
        for member in roster:
            if member.is_official:
                continue
            birthdate = member.birthdate_value
            if not birthdate:
                continue
            try:
                occurrence = date(match_date.year, birthdate.month, birthdate.day)
            except ValueError:
                # Defensive: skip invalid dates such as 29.02 in non-leap years
                try:
                    occurrence = date(match_date.year - 1, birthdate.month, birthdate.day)
                except ValueError:
                    continue
            if occurrence > match_date:
                occurrence = date(match_date.year - 1, birthdate.month, birthdate.day)
            delta = (match_date - occurrence).days
            if delta < 0 or delta > 7:
                continue
            age_value = calculate_age(birthdate, match_date)
            if delta == 0:
                if age_value is not None:
                    note = f"{member.name.strip()} hat heute Geburtstag ({age_value} Jahre)!"
                else:
                    note = f"{member.name.strip()} hat heute Geburtstag!"
            else:
                date_label = occurrence.strftime("%d.%m.%Y")
                if age_value is not None:
                    note = (
                        f"{member.name.strip()} hatte am {date_label} Geburtstag"
                        f" ({age_value} Jahre)."
                    )
                else:
                    note = f"{member.name.strip()} hatte am {date_label} Geburtstag."
            notes.append((delta, note))
    notes.sort(key=lambda item: (item[0], item[1]))
    return [note for _, note in notes]


def format_transfer_list(items: Sequence[TransferItem]) -> str:
    if not items:
        return "<li>Keine Wechsel gemeldet.</li>"

    rendered: List[str] = []
    current_category: Optional[str] = None
    for item in items:
        if item.category and item.category != current_category:
            rendered.append(
                f"<li class=\"transfer-category\">{escape(item.category)}</li>"
            )
            current_category = item.category
        parts: List[str] = []
        name_part = item.name.strip()
        if name_part:
            parts.append(name_part)
        type_label = item.type_code.strip()
        if type_label:
            parts.append(type_label)
        nationality = item.nationality.strip()
        if nationality:
            parts.append(nationality)
        info = item.info.strip()
        if info:
            parts.append(info)
        related = item.related_club.strip()
        if related:
            parts.append(related)
        if not parts:
            continue
        rendered.append(
            f"<li class=\"transfer-line\">{' | '.join(escape(part) for part in parts)}</li>"
        )
    return "\n          ".join(rendered)



def _format_season_results_section(
    data: Optional[Mapping[str, Any]], opponent_name: str
) -> str:
    if not data or not isinstance(data, Mapping):
        return ""

    raw_title = data.get("title")
    if isinstance(raw_title, str) and raw_title.strip():
        title = raw_title.strip()
    else:
        title = "Ergebnis der Saison 2024/25"

    teams_raw = data.get("teams")
    teams_by_key: Dict[str, Dict[str, Any]] = {}
    if isinstance(teams_raw, Sequence):
        for entry in teams_raw:
            if not isinstance(entry, Mapping):
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            key = normalize_name(name)
            if not key or key in teams_by_key:
                continue
            details_raw = entry.get("details")
            details: List[str] = []
            if isinstance(details_raw, Sequence):
                for item in details_raw:
                    if not item:
                        continue
                    details.append(str(item).strip())
            teams_by_key[key] = {"name": name, "details": details}

    if not teams_by_key:
        links_raw = data.get("links")
        has_links = bool(
            isinstance(links_raw, Sequence)
            and any(
                isinstance(entry, Mapping)
                and str(entry.get("label") or "").strip()
                and str(entry.get("url") or "").strip()
                for entry in links_raw
            )
        )
        if not has_links:
            return ""

    normalized_opponent = normalize_name(opponent_name)
    normalized_usc = normalize_name(USC_CANONICAL_NAME)

    selected: List[Dict[str, Any]] = []
    missing_opponent = False
    if normalized_opponent and normalized_opponent in teams_by_key:
        selected.append(teams_by_key[normalized_opponent])
    elif normalized_opponent:
        missing_opponent = True

    usc_entry = teams_by_key.get(normalized_usc)
    if usc_entry and (not selected or usc_entry["name"] != selected[0]["name"]):
        selected.append(usc_entry)
    elif not selected and usc_entry:
        selected.append(usc_entry)

    status_message = ""
    if not selected:
        status_message = "Keine Saisoninformationen verfügbar."
    elif missing_opponent:
        status_message = (
            f"Für {pretty_name(opponent_name)} liegen keine Saisoninformationen vor."
        )

    cards_markup: List[str] = []
    for team in selected:
        name = team.get("name")
        if not name:
            continue
        details = [detail for detail in team.get("details", []) if detail]
        details_html = ""
        if details:
            detail_items = "".join(
                f"\n              <li>{escape(str(detail))}</li>" for detail in details
            )
            details_html = (
                "\n            <ul class=\"season-results-list\">"
                f"{detail_items}\n            </ul>"
            )
        cards_markup.append(
            "        <article class=\"season-results-card\">\n"
            f"          <h3>{escape(str(name))}</h3>{details_html}\n"
            "        </article>"
        )

    if not cards_markup:
        cards_markup.append(
            "        <p class=\"season-results-fallback\">Keine Saisoninformationen verfügbar.</p>"
        )

    links_raw = data.get("links")
    link_block: List[str] = []
    if isinstance(links_raw, Sequence):
        link_items: List[str] = []
        for entry in links_raw:
            if not isinstance(entry, Mapping):
                continue
            label = str(entry.get("label") or "").strip()
            url = str(entry.get("url") or "").strip()
            if not label or not url:
                continue
            link_items.append(
                f"          <li><a href=\"{escape(url)}\" rel=\"noopener\" target=\"_blank\">{escape(label)}</a></li>"
            )
        if link_items:
            link_block = [
                "      <div class=\"season-results-links\">",
                "        <h3>Weitere Informationen</h3>",
                "        <ul class=\"season-results-link-list\">",
                *link_items,
                "        </ul>",
                "      </div>",
            ]

    header_lines = [
        "      <div class=\"season-results-header\">",
        f"        <h2>{escape(title)}</h2>",
    ]
    if status_message:
        header_lines.append(
            f"        <p class=\"season-results-status\">{escape(status_message)}</p>"
        )
    header_lines.append("      </div>")

    section_lines = [
        "    <section class=\"season-results\">",
        *header_lines,
        "      <div class=\"season-results-grid\">",
        *cards_markup,
        "      </div>",
    ]
    section_lines.extend(link_block)
    section_lines.append("    </section>")

    return "\n".join(section_lines)


def build_html_report(
    *,
    next_home: Match,
    usc_recent: List[Match],
    opponent_recent: List[Match],
    usc_next: Optional[Match] = None,
    opponent_next: Optional[Match] = None,
    usc_news: Sequence[NewsItem],
    opponent_news: Sequence[NewsItem],
    usc_instagram: Sequence[str],
    opponent_instagram: Sequence[str],
    usc_roster: Sequence[RosterMember],
    opponent_roster: Sequence[RosterMember],
    usc_transfers: Sequence[TransferItem],
    opponent_transfers: Sequence[TransferItem],
    usc_photo: Optional[str],
    opponent_photo: Optional[str],
    season_results: Optional[Mapping[str, Any]] = None,
    generated_at: Optional[datetime] = None,
    font_scale: float = 1.0,
    match_stats: Optional[Mapping[str, Sequence[MatchStatsTotals]]] = None,
    mvp_rankings: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> str:
    heading = pretty_name(next_home.away_team)
    kickoff_dt = next_home.kickoff.astimezone(BERLIN_TZ)
    kickoff_date = kickoff_dt.strftime("%d.%m.%Y")
    kickoff_weekday = GERMAN_WEEKDAYS.get(
        kickoff_dt.weekday(), kickoff_dt.strftime("%a")
    )
    kickoff_time = kickoff_dt.strftime("%H:%M")
    kickoff = f"{kickoff_date} ({kickoff_weekday}) {kickoff_time}"
    match_day = kickoff_dt.date()
    location = pretty_name(next_home.location)
    usc_url = get_team_homepage(USC_CANONICAL_NAME) or USC_HOMEPAGE
    opponent_url = get_team_homepage(next_home.away_team)

    def _combine_matches(
        next_match: Optional[Match],
        recent_matches: List[Match],
    ) -> str:
        combined: List[str] = []
        seen: set[tuple[datetime, str, str]] = set()

        ordered: List[Match] = []
        if next_match:
            ordered.append(next_match)
        ordered.extend(recent_matches)

        for match in ordered:
            signature = (
                match.kickoff,
                normalize_name(match.home_team),
                normalize_name(match.away_team),
            )
            if signature in seen:
                continue
            seen.add(signature)
            stats_payload: Optional[Sequence[MatchStatsTotals]] = None
            if match_stats and match.stats_url:
                stats_payload = match_stats.get(match.stats_url)
            combined.append(format_match_line(match, stats=stats_payload))

        if not combined:
            return "<li>Keine Daten verfügbar.</li>"
        return "\n      ".join(combined)

    usc_items = _combine_matches(usc_next, usc_recent)
    opponent_items = _combine_matches(opponent_next, opponent_recent)

    usc_news_items = format_news_list(usc_news)
    opponent_news_items = format_news_list(opponent_news)
    usc_instagram_items = format_instagram_list(usc_instagram)
    opponent_instagram_items = format_instagram_list(opponent_instagram)
    season_results_section = _format_season_results_section(
        season_results, next_home.away_team
    )
    usc_roster_items = format_roster_list(usc_roster, match_date=match_day)
    opponent_roster_items = format_roster_list(opponent_roster, match_date=match_day)
    usc_transfer_items = format_transfer_list(usc_transfers)
    opponent_transfer_items = format_transfer_list(opponent_transfers)
    mvp_section_html = format_mvp_rankings_section(
        mvp_rankings,
        usc_name=USC_CANONICAL_NAME,
        opponent_name=next_home.away_team,
    )

    navigation_links = [
        ("aufstellungen.html", "Startaufstellungen der letzten Begegnungen"),
        ("internationale_spiele.html", "Internationale Spiele 2025/26"),
    ]
    lineup_link_items = "\n        ".join(
        f"<li><a href=\"{escape(url)}\">{escape(label)}</a></li>"
        for url, label in navigation_links
    )

    opponent_photo_block = ""
    if opponent_photo:
        opponent_photo_block = (
            "          <figure class=\"team-photo\">"
            f"<img src=\"{escape(opponent_photo)}\" alt=\"Teamfoto {escape(heading)}\" />"
            f"<figcaption>Teamfoto {escape(heading)}</figcaption>"
            "</figure>\n"
        )

    usc_photo_block = ""
    if usc_photo:
        usc_photo_block = (
            "          <figure class=\"team-photo\">"
            f"<img src=\"{escape(usc_photo)}\" alt=\"Teamfoto {escape(USC_CANONICAL_NAME)}\" />"
            f"<figcaption>Teamfoto {escape(USC_CANONICAL_NAME)}</figcaption>"
            "</figure>\n"
        )
    meta_lines = [
        f"<p><strong>Spieltermin:</strong> {escape(kickoff)} Uhr</p>",
        f"<p><strong>Austragungsort:</strong> {escape(location)}</p>",
    ]

    referees = list(next_home.referees)
    for idx in range(1, 3):
        if idx <= len(referees):
            referee_name = referees[idx - 1]
        else:
            referee_name = "noch nicht veröffentlicht"
        meta_lines.append(
            f"<p><strong>{idx}. Schiedsrichter*in:</strong> {escape(referee_name)}</p>"
        )

    meta_lines.append(
        f"<p><a class=\"meta-link\" href=\"{escape(TABLE_URL)}\">Tabelle der Volleyball Bundesliga</a></p>"
    )
    if usc_url:
        meta_lines.append(
            f"<p><a class=\"meta-link\" href=\"{escape(usc_url)}\">Homepage USC Münster</a></p>"
        )
    if opponent_url:
        meta_lines.append(
            f"<p><a class=\"meta-link\" href=\"{escape(opponent_url)}\">Homepage {escape(heading)}</a></p>"
        )
    meta_html = "\n      ".join(meta_lines)

    birthday_notes = collect_birthday_notes(
        match_day,
        (
            (USC_CANONICAL_NAME, usc_roster),
            (heading, opponent_roster),
        ),
    )
    notes_html = ""
    if birthday_notes:
        note_items = "\n        ".join(
            f"<li>{escape(note)}</li>" for note in birthday_notes
        )
        notes_html = (
            "\n"
            "    <section class=\"notice-group\">\n"
            "      <h2>Bemerkungen</h2>\n"
            "      <ul class=\"notice-list\">\n"
            f"        {note_items}\n"
            "      </ul>\n"
            "    </section>\n"
            "\n"
        )

    update_note_html = ""
    if generated_at:
        generated_label = format_generation_timestamp(generated_at)
        update_note_html = (
            "    <footer class=\"page-footer\">\n"
            "      <p class=\"update-note\" role=\"status\">\n"
            "        <span aria-hidden=\"true\">📅</span>\n"
            f"        <span><strong>Aktualisiert am</strong> {escape(generated_label)}</span>\n"
            "      </p>\n"
            "    </footer>\n"
            "\n"
        )

    font_scale = max(0.3, min(font_scale, 3.0))
    scale_value = f"{font_scale:.4f}".rstrip("0").rstrip(".")
    if not scale_value:
        scale_value = "1"

    html = f"""<!DOCTYPE html>
<html lang=\"de\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Nächster USC-Heimgegner</title>
  <style>
    :root {{
      color-scheme: light dark;
      --font-scale: {scale_value};
      --accordion-opponent-bg: #e0f2fe;
      --accordion-opponent-shadow: rgba(30, 64, 175, 0.08);
      --accordion-usc-bg: #dcfce7;
      --accordion-usc-shadow: rgba(22, 163, 74, 0.08);
    }}
    body {{
      margin: 0;
      font-family: \"Inter\", \"Segoe UI\", -apple-system, BlinkMacSystemFont, \"Helvetica Neue\", Arial, sans-serif;
      line-height: 1.6;
      font-size: calc(var(--font-scale) * clamp(0.95rem, 1.8vw, 1.05rem));
      background: #f5f7f9;
      color: #1f2933;
    }}
    main {{
      max-width: 56rem;
      margin: 0 auto;
      padding: clamp(0.6rem, 2.5vw, 1.2rem) clamp(0.9rem, 3vw, 2.4rem);
    }}
    h1 {{
      color: #004c54;
      font-size: calc(var(--font-scale) * clamp(1.55rem, 4.5vw, 2.35rem));
      margin: 0 0 1.25rem 0;
    }}
    h2 {{
      font-size: calc(var(--font-scale) * clamp(1.15rem, 3.6vw, 1.6rem));
      margin-bottom: 1rem;
    }}
    section {{
      margin-top: clamp(1.2rem, 3vw, 2rem);
    }}
    .meta {{
      display: grid;
      gap: 0.25rem;
      margin: 0 0 1.3rem 0;
      padding: 0;
    }}
    .meta p {{
      margin: 0;
    }}
    .update-note {{
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      padding: 0.25rem 0.6rem;
      background: #ecfdf5;
      color: #047857;
      border-radius: 999px;
      font-size: calc(var(--font-scale) * 0.7rem);
      font-weight: 600;
      border: 1px solid #bbf7d0;
    }}
    .update-note span {{
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
    }}
    .page-footer {{
      margin-top: clamp(1.75rem, 4vw, 2.75rem);
      display: flex;
      justify-content: center;
    }}
    .match-list {{
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 0.75rem;
    }}
    .match-list li {{
      background: #ffffff;
      border-radius: 0.8rem;
      padding: 0.85rem clamp(0.9rem, 2.6vw, 1.3rem);
      box-shadow: 0 10px 30px rgba(0, 76, 84, 0.08);
    }}
    .lineup-link {{
      margin-top: clamp(0.75rem, 2.5vw, 1.4rem);
      display: flex;
      justify-content: center;
    }}
    .lineup-link ul {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: clamp(0.6rem, 2vw, 1rem);
    }}
    .lineup-link li {{
      display: flex;
    }}
    .lineup-link a {{
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.6rem 1.2rem;
      border-radius: 999px;
      background: #0f766e;
      color: #ffffff;
      font-weight: 600;
      text-decoration: none;
      box-shadow: 0 12px 28px rgba(15, 118, 110, 0.25);
      transition: transform 0.15s ease, box-shadow 0.15s ease;
    }}
    .lineup-link a:hover,
    .lineup-link a:focus-visible {{
      transform: translateY(-1px);
      box-shadow: 0 16px 32px rgba(15, 118, 110, 0.3);
      outline: none;
    }}
    .match-line {{
      display: flex;
      flex-direction: column;
      gap: 0.45rem;
    }}
    .match-header {{
      font-weight: 600;
      color: inherit;
    }}
    .match-result {{
      font-family: \"Fira Mono\", \"SFMono-Regular\", Menlo, Consolas, monospace;
      font-size: calc(var(--font-scale) * 0.9rem);
      color: #0f766e;
    }}
    .match-meta {{
      font-size: calc(var(--font-scale) * 0.85rem);
      color: #475569;
      display: flex;
      flex-wrap: wrap;
      gap: 0.3rem 0.75rem;
      align-items: center;
    }}
    .match-meta span {{
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
    }}
    .match-meta a {{
      color: #1d4ed8;
      font-weight: 600;
      text-decoration: none;
    }}
    .match-meta a:hover,
    .match-meta a:focus-visible {{
      text-decoration: underline;
      outline: none;
    }}
    .match-stats {{
      margin-top: clamp(0.45rem, 1.4vw, 0.85rem);
      border-radius: 0.85rem;
      background: #f8fafc;
      border: 1px solid rgba(15, 118, 110, 0.18);
      padding: 0.75rem 1rem;
    }}
    .match-stats summary {{
      cursor: pointer;
      list-style: none;
      display: flex;
      align-items: center;
      gap: 0.45rem;
      font-weight: 600;
      font-size: calc(var(--font-scale) * 0.92rem);
    }}
    .match-stats summary::-webkit-details-marker {{
      display: none;
    }}
    .match-stats summary::after {{
      content: "▾";
      margin-left: auto;
      font-size: calc(var(--font-scale) * 0.9rem);
      transition: transform 0.2s ease;
    }}
    .match-stats[open] summary::after {{
      transform: rotate(180deg);
    }}
    .match-stats-content {{
      margin-top: 0.75rem;
      display: grid;
      gap: clamp(0.75rem, 2vw, 1.1rem);
    }}
    .match-stats-table-wrapper {{
      overflow-x: auto;
    }}
    .match-stats-table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      background: #ffffff;
      border-radius: 0.75rem;
      box-shadow: 0 12px 26px rgba(15, 23, 42, 0.08);
      border: 1px solid rgba(148, 163, 184, 0.35);
      min-width: 22rem;
    }}
    .match-stats-table thead th {{
      background: rgba(15, 118, 110, 0.12);
      color: #0f766e;
      font-size: calc(var(--font-scale) * 0.8rem);
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.02em;
      padding: 0.55rem 0.75rem;
      text-align: center;
    }}
    .match-stats-table thead th:first-child {{
      text-align: left;
    }}
    .match-stats-table tbody th {{
      text-align: left;
      padding: 0.65rem 0.85rem;
      font-size: calc(var(--font-scale) * 0.9rem);
      font-weight: 600;
      color: #0f172a;
    }}
    .match-stats-table tbody td {{
      text-align: center;
      padding: 0.65rem 0.7rem;
      font-size: calc(var(--font-scale) * 0.9rem);
      font-weight: 500;
      color: #1f2937;
    }}
    .match-stats-table tbody tr + tr th,
    .match-stats-table tbody tr + tr td {{
      border-top: 1px solid #e2e8f0;
    }}
    .match-stats-table tbody tr[data-team-role="usc"] {{
      background: #dcfce7;
      color: #047857;
    }}
    .match-stats-table tbody tr[data-team-role="usc"] th,
    .match-stats-table tbody tr[data-team-role="usc"] td {{
      color: inherit;
    }}
    .match-stats-table tbody tr[data-team-role="home"],
    .match-stats-table tbody tr[data-team-role="away"] {{
      background: #e0f2fe;
      color: #1d4ed8;
    }}
    .match-stats-table tbody tr[data-team-role="home"] th,
    .match-stats-table tbody tr[data-team-role="home"] td,
    .match-stats-table tbody tr[data-team-role="away"] th,
    .match-stats-table tbody tr[data-team-role="away"] td {{
      color: inherit;
    }}
    .match-stats-card {{
      border-radius: 0.75rem;
      background: #ffffff;
      padding: 0.75rem 0.95rem;
      box-shadow: 0 12px 26px rgba(15, 23, 42, 0.08);
      border: 1px solid rgba(148, 163, 184, 0.35);
    }}
    .match-stats-card[data-team-role="usc"] {{
      border-color: rgba(45, 212, 191, 0.55);
      box-shadow: 0 14px 30px rgba(45, 212, 191, 0.16);
    }}
    .match-stats-card[data-team-role="home"],
    .match-stats-card[data-team-role="away"] {{
      border-color: rgba(59, 130, 246, 0.35);
    }}
    .match-stats-card h4 {{
      margin: 0 0 0.5rem 0;
      font-size: calc(var(--font-scale) * 0.95rem);
      font-weight: 600;
      color: #0f172a;
    }}
    .match-stats-card pre {{
      margin: 0;
      font-family: \"Fira Mono\", \"SFMono-Regular\", Menlo, Consolas, monospace;
      font-size: calc(var(--font-scale) * 0.75rem);
      line-height: 1.4;
      white-space: pre;
      overflow-x: auto;
      padding: 0.5rem 0.65rem;
      background: rgba(15, 23, 42, 0.04);
      border-radius: 0.6rem;
      color: #1f2937;
    }}
    .news-group,
    .roster-group,
    .transfer-group {{
      margin-top: clamp(1.5rem, 3.5vw, 2.5rem);
      display: grid;
      gap: 0.75rem;
    }}
    .accordion {{
      border-radius: 0.85rem;
      overflow: hidden;
      background: var(--accordion-opponent-bg);
      box-shadow: 0 18px 40px var(--accordion-opponent-shadow);
      border: none;
    }}
    .roster-group details:nth-of-type(2),
    .transfer-group details:nth-of-type(2),
    .news-group details:nth-of-type(2) {{
      background: var(--accordion-usc-bg);
      box-shadow: 0 18px 40px var(--accordion-usc-shadow);
    }}
    .accordion summary {{
      cursor: pointer;
      padding: 0.85rem 1.2rem;
      font-weight: 600;
      display: flex;
      align-items: center;
      justify-content: space-between;
      list-style: none;
      font-size: calc(var(--font-scale) * clamp(1rem, 2.6vw, 1.2rem));
    }}
    .accordion summary::-webkit-details-marker {{
      display: none;
    }}
    .accordion summary::after {{
      content: \"▾\";
      font-size: calc(var(--font-scale) * 1rem);
      transition: transform 0.2s ease;
    }}
    .accordion[open] summary::after {{
      transform: rotate(180deg);
    }}
    .accordion-content {{
      padding: 0 1.2rem 1.2rem;
    }}
    .news-list {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }}
    .news-list li {{
      margin: 0;
      padding: 0;
    }}
    .news-meta {{
      display: block;
      font-size: calc(var(--font-scale) * 0.85rem);
      color: #64748b;
      margin-top: 0.2rem;
    }}
    .mvp-group {{
      margin-top: clamp(1.5rem, 3.5vw, 2.5rem);
    }}
    .mvp-overview {{
      border-radius: 0.8rem;
      border: none;
      background: #ffffff;
      box-shadow: 0 14px 30px rgba(15, 118, 110, 0.14);
      overflow: hidden;
    }}
    .mvp-overview summary {{
      cursor: pointer;
      padding: 0.85rem 1.2rem;
      font-weight: 600;
      display: flex;
      align-items: center;
      justify-content: space-between;
      list-style: none;
      font-size: calc(var(--font-scale) * clamp(1rem, 2.4vw, 1.15rem));
    }}
    .mvp-overview summary::-webkit-details-marker {{
      display: none;
    }}
    .mvp-overview summary::after {{
      content: "▾";
      font-size: calc(var(--font-scale) * 1rem);
      transition: transform 0.2s ease;
    }}
    .mvp-overview[open] summary::after {{
      transform: rotate(180deg);
    }}
    .mvp-overview-content {{
      padding: 0 1.2rem 1.2rem;
      display: grid;
      gap: clamp(0.6rem, 2vw, 1.1rem);
    }}
    .mvp-note {{
      margin: 0;
      font-size: calc(var(--font-scale) * 0.85rem);
      color: #475569;
    }}
    .mvp-legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.6rem;
      align-items: center;
    }}
    .mvp-legend-item {{
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.35rem 0.75rem;
      border-radius: 999px;
      font-size: calc(var(--font-scale) * 0.75rem);
      font-weight: 600;
      background: rgba(15, 23, 42, 0.05);
      color: #0f172a;
    }}
    .mvp-legend-item::before {{
      content: "";
      width: 0.65rem;
      height: 0.65rem;
      border-radius: 50%;
      box-shadow: inset 0 0 0 2px rgba(15, 23, 42, 0.15);
    }}
    .mvp-legend-item[data-team="usc"]::before {{
      background: #16a34a;
    }}
    .mvp-legend-item[data-team="opponent"]::before {{
      background: #2563eb;
    }}
    .mvp-category {{
      border-radius: 0.8rem;
      border: 1px solid #e2e8f0;
      background: #f8fafc;
      overflow: hidden;
    }}
    .mvp-category summary {{
      cursor: pointer;
      padding: 0.85rem 1.05rem;
      font-weight: 600;
      display: flex;
      align-items: center;
      justify-content: space-between;
      list-style: none;
      font-size: calc(var(--font-scale) * clamp(0.95rem, 2.2vw, 1.1rem));
      gap: 0.6rem;
      background: rgba(15, 118, 110, 0.08);
    }}
    .mvp-category summary::-webkit-details-marker {{
      display: none;
    }}
    .mvp-category summary::after {{
      content: "▾";
      font-size: calc(var(--font-scale) * 0.95rem);
      transition: transform 0.2s ease;
      color: inherit;
    }}
    .mvp-category[open] summary::after {{
      transform: rotate(180deg);
    }}
    .mvp-category-title {{
      flex: 1;
    }}
    .mvp-category-badge {{
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      padding: 0.3rem 0.65rem;
      border-radius: 999px;
      background: rgba(15, 118, 110, 0.14);
      color: #0f4c75;
      font-weight: 700;
      font-size: calc(var(--font-scale) * 0.7rem);
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }}
    .mvp-category-content {{
      padding: 0.9rem 1.05rem 1.1rem;
      display: grid;
      gap: 0.7rem;
    }}
    .mvp-list {{
      margin: 0;
      padding: 0;
      list-style: none;
      display: grid;
      gap: 0.55rem;
    }}
    .mvp-entry {{
      display: grid;
      grid-template-columns: minmax(4.75rem, auto) 1fr minmax(4.5rem, auto);
      gap: 0.6rem;
      align-items: center;
      padding: 0.6rem 0.75rem;
      border-radius: 0.7rem;
      background: rgba(15, 23, 42, 0.05);
      box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.08);
    }}
    .mvp-entry-rank {{
      font-weight: 700;
      font-size: calc(var(--font-scale) * 0.95rem);
      color: #0f172a;
    }}
    .mvp-entry-info {{
      display: flex;
      flex-direction: column;
      gap: 0.15rem;
    }}
    .mvp-entry-name {{
      font-weight: 600;
      color: #0f172a;
      font-size: calc(var(--font-scale) * 0.95rem);
    }}
    .mvp-entry-meta {{
      font-size: calc(var(--font-scale) * 0.78rem);
      color: #475569;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }}
    .mvp-entry-score {{
      font-weight: 700;
      font-size: calc(var(--font-scale) * 0.95rem);
      color: #0f4c75;
      justify-self: end;
    }}
    .mvp-entry[data-team="opponent"] {{
      background: rgba(59, 130, 246, 0.12);
      box-shadow: inset 0 0 0 1px rgba(37, 99, 235, 0.22);
    }}
    .mvp-entry[data-team="opponent"] .mvp-entry-score {{
      color: #1d4ed8;
    }}
    .mvp-entry[data-team="usc"] {{
      background: rgba(16, 185, 129, 0.12);
      box-shadow: inset 0 0 0 1px rgba(5, 150, 105, 0.24);
    }}
    .mvp-entry[data-team="usc"] .mvp-entry-score {{
      color: #047857;
    }}
    @media (max-width: 38rem) {{
      .mvp-category summary {{
        flex-direction: column;
        align-items: flex-start;
        gap: 0.4rem;
      }}
      .mvp-entry {{
        grid-template-columns: minmax(4.25rem, auto) 1fr;
        grid-template-areas: \"rank score\" \"info info\";
        row-gap: 0.4rem;
      }}
      .mvp-entry-rank {{
        grid-area: rank;
      }}
      .mvp-entry-score {{
        grid-area: score;
      }}
      .mvp-entry-info {{
        grid-area: info;
      }}
    }}
    .mvp-empty {{
      margin: 0;
      font-size: calc(var(--font-scale) * 0.9rem);
      color: #475569;
    }}
    .transfer-list {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 0.65rem;
    }}
    .transfer-category {{
      font-weight: 700;
      color: #1d4ed8;
      padding-top: 0.35rem;
      margin: 0;
    }}
    .transfer-line {{
      font-size: calc(var(--font-scale) * 0.95rem);
      font-weight: 500;
      color: inherit;
      word-break: break-word;
    }}
    .team-photo {{
      margin: 0 0 1.1rem 0;
    }}
    .team-photo img {{
      width: 100%;
      border-radius: 0.85rem;
      display: block;
    }}
    .team-photo figcaption {{
      font-size: calc(var(--font-scale) * 0.85rem);
      color: #64748b;
      margin-top: 0.35rem;
      text-align: center;
    }}
    .roster-list {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 0.8rem;
    }}
    .roster-item {{
      display: grid;
      grid-template-columns: minmax(3.6rem, auto) 1fr;
      gap: 0.75rem;
      align-items: center;
    }}
    .roster-number {{
      font-family: \"Fira Mono\", \"SFMono-Regular\", Menlo, Consolas, monospace;
      font-weight: 600;
      font-size: calc(var(--font-scale) * 0.95rem);
      background: #bae6fd;
      color: #1f2933;
      border-radius: 0.65rem;
      padding: 0.35rem 0.65rem;
      text-align: center;
    }}
    .roster-official .roster-number {{
      background: #e2e8f0;
    }}
    .roster-text {{
      display: flex;
      flex-direction: column;
      gap: 0.2rem;
    }}
    .roster-name {{
      font-weight: 600;
      font-size: calc(var(--font-scale) * 1rem);
    }}
    .roster-details {{
      font-size: calc(var(--font-scale) * 0.82rem);
      color: #475569;
      line-height: 1.35;
    }}
    .notice-group {{
      margin-top: clamp(1.4rem, 3vw, 2rem);
    }}
    .notice-list {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 0.65rem;
    }}
    .notice-list li {{
      background: linear-gradient(135deg, #fef3c7, #fde68a);
      border-radius: 0.85rem;
      padding: clamp(0.85rem, 2.8vw, 1.15rem);
      font-weight: 600;
      box-shadow: 0 16px 34px rgba(250, 204, 21, 0.22);
    }}
    .instagram-group {{
      margin-top: clamp(1.5rem, 3.5vw, 2.5rem);
    }}
    .instagram-grid {{
      display: grid;
      gap: 1.2rem;
      grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
    }}
    .instagram-card {{
      background: #ffffff;
      border-radius: 0.85rem;
      padding: clamp(1rem, 3vw, 1.4rem);
      box-shadow: 0 12px 28px rgba(15, 118, 110, 0.12);
    }}
    .instagram-card h3 {{
      margin: 0 0 0.75rem 0;
      font-size: calc(var(--font-scale) * clamp(1.05rem, 3vw, 1.3rem));
    }}
    .instagram-list {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 0.35rem;
    }}
    .season-results {{
      margin-top: clamp(1.5rem, 3.5vw, 2.5rem);
    }}
    .season-results-header {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.6rem 1.25rem;
      align-items: baseline;
      margin-bottom: clamp(0.75rem, 2.5vw, 1.25rem);
    }}
    .season-results-header h2 {{
      margin: 0;
    }}
    .season-results-status {{
      margin: 0;
      font-size: calc(var(--font-scale) * 0.8rem);
      color: #475569;
    }}
    .season-results-grid {{
      display: grid;
      gap: clamp(1rem, 3vw, 1.5rem);
      grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
    }}
    .season-results-card {{
      background: #ffffff;
      border-radius: 0.85rem;
      padding: clamp(1rem, 3vw, 1.4rem);
      box-shadow: 0 12px 28px rgba(15, 118, 110, 0.12);
      display: grid;
      gap: 0.6rem;
    }}
    .season-results-card h3 {{
      margin: 0;
      font-size: calc(var(--font-scale) * clamp(1.05rem, 3vw, 1.3rem));
      color: #0f172a;
    }}
    .season-results-list {{
      margin: 0;
      padding-left: 1rem;
      display: grid;
      gap: 0.35rem;
      font-size: calc(var(--font-scale) * 0.9rem);
      color: #1f2933;
    }}
    .season-results-fallback {{
      margin: 0;
      font-size: calc(var(--font-scale) * 0.9rem);
      color: #475569;
    }}
    .season-results-links {{
      margin-top: clamp(1rem, 3vw, 1.75rem);
      background: #f8fafc;
      border-radius: 0.85rem;
      padding: clamp(1rem, 3vw, 1.4rem);
      box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.35);
    }}
    .season-results-links h3 {{
      margin: 0 0 0.75rem 0;
      font-size: calc(var(--font-scale) * clamp(0.95rem, 2.5vw, 1.1rem));
      color: #1f2937;
    }}
    .season-results-link-list {{
      margin: 0;
      padding-left: 1rem;
      display: grid;
      gap: 0.4rem;
    }}
    .season-results-link-list a {{
      color: #1d4ed8;
      font-weight: 600;
      text-decoration: none;
    }}
    .season-results-link-list a:hover,
    .season-results-link-list a:focus-visible {{
      text-decoration: underline;
      outline: none;
    }}
    .meta-link {{
      font-weight: 600;
    }}
    a {{
      color: #0f766e;
    }}
    a:hover,
    a:focus {{
      text-decoration: underline;
    }}
    .match-meta a {{
      color: #1d4ed8;
      font-weight: 600;
    }}
    .match-meta a:hover,
    .match-meta a:focus-visible {{
      text-decoration: underline;
      outline: none;
    }}
    @media (max-width: 40rem) {{
      body {{
        font-size: calc(var(--font-scale) * 0.85rem);
      }}
      h1 {{
        font-size: calc(var(--font-scale) * 1.6rem);
      }}
      h2 {{
        font-size: calc(var(--font-scale) * 1.1rem);
      }}
      .match-list li {{
        padding: 0.85rem 1rem;
      }}
      .lineup-link ul {{
        flex-direction: column;
        align-items: center;
        gap: 0.75rem;
      }}
      .lineup-link li {{
        width: 100%;
        justify-content: center;
      }}
      .lineup-link a {{
        width: min(22rem, 100%);
        justify-content: center;
      }}
      .match-result {{
        font-size: calc(var(--font-scale) * 0.8rem);
      }}
      .match-stats summary {{
        font-size: calc(var(--font-scale) * 0.9rem);
      }}
      .match-stats-table {{
        min-width: min(18rem, 100%);
      }}
      .match-stats-table thead th {{
        font-size: calc(var(--font-scale) * 0.68rem);
        padding: 0.35rem 0.45rem;
      }}
      .match-stats-table tbody th,
      .match-stats-table tbody td {{
        font-size: calc(var(--font-scale) * 0.78rem);
        padding: 0.4rem 0.45rem;
      }}
      .accordion summary {{
        font-size: calc(var(--font-scale) * 1.05rem);
      }}
      .mvp-overview summary {{
        font-size: calc(var(--font-scale) * 1.05rem);
      }}
      .roster-item {{
        grid-template-columns: minmax(3rem, auto) 1fr;
      }}
      .roster-number {{
        font-size: calc(var(--font-scale) * 0.8rem);
        padding: 0.3rem 0.5rem;
      }}
      .team-photo {{
        margin-bottom: 0.9rem;
      }}
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --accordion-opponent-bg: #1c3f5f;
        --accordion-opponent-shadow: rgba(56, 189, 248, 0.28);
        --accordion-usc-bg: #1a4f3a;
        --accordion-usc-shadow: rgba(74, 222, 128, 0.26);
      }}
      body {{
        background: #0e1b1f;
        color: #e6f1f3;
      }}
      h1,
      h2,
      h3 {{
        color: #f1f5f9;
      }}
      .match-list li {{
        background: #132a30;
        box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
      }}
      .match-stats {{
        background: #132a30;
        border-color: rgba(45, 212, 191, 0.35);
      }}
      .match-stats summary {{
        color: #e2f3f7;
      }}
      .match-stats-table {{
        background: #0f1f24;
        border-color: rgba(94, 234, 212, 0.25);
        box-shadow: 0 16px 34px rgba(0, 0, 0, 0.45);
      }}
      .match-stats-table thead th {{
        background: rgba(94, 234, 212, 0.16);
        color: #5eead4;
      }}
      .match-stats-table tbody tr + tr th,
      .match-stats-table tbody tr + tr td {{
        border-color: rgba(148, 163, 184, 0.35);
      }}
      .match-stats-table tbody th,
      .match-stats-table tbody td {{
        color: #e2f3f7;
      }}
      .match-stats-table tbody tr[data-team-role="usc"] {{
        background: rgba(22, 163, 74, 0.25);
        color: #bbf7d0;
      }}
      .match-stats-table tbody tr[data-team-role="home"],
      .match-stats-table tbody tr[data-team-role="away"] {{
        background: rgba(59, 130, 246, 0.18);
        color: #bfdbfe;
      }}
      .match-stats-card {{
        background: #0f1f24;
        border-color: rgba(94, 234, 212, 0.25);
        box-shadow: 0 16px 34px rgba(0, 0, 0, 0.45);
      }}
      .match-stats-card h4 {{
        color: #f0f9ff;
      }}
      .match-stats-card pre {{
        background: rgba(15, 118, 110, 0.22);
        color: #f1f5f9;
      }}
      .lineup-link a {{
        background: #14b8a6;
        color: #022c22;
        box-shadow: 0 16px 32px rgba(20, 184, 166, 0.35);
      }}
      .accordion {{
        background: var(--accordion-opponent-bg);
        box-shadow: 0 18px 40px var(--accordion-opponent-shadow);
      }}
      .mvp-overview {{
        background: #132a30;
        box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
      }}
      .mvp-overview summary {{
        color: #f1f5f9;
      }}
      .mvp-note {{
        color: #cbd5f5;
      }}
      .mvp-card {{
        background: #132a30;
        box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
      }}
      .mvp-card summary {{
        color: #f1f5f9;
      }}
      .roster-group details:nth-of-type(2),
      .transfer-group details:nth-of-type(2),
      .news-group details:nth-of-type(2) {{
        background: var(--accordion-usc-bg);
        box-shadow: 0 18px 40px var(--accordion-usc-shadow);
      }}
      .instagram-card {{
        background: #132a30;
        box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
      }}
      .season-results-card {{
        background: #132a30;
        box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
      }}
      .season-results-card h3 {{
        color: #f1f5f9;
      }}
      .season-results-list {{
        color: #cbd5f5;
      }}
      .season-results-fallback {{
        color: #94a3b8;
      }}
      .season-results-links {{
        background: #0f1f24;
        box-shadow: inset 0 0 0 1px rgba(94, 234, 212, 0.25);
      }}
      .season-results-links h3 {{
        color: #e6f1f3;
      }}
      .season-results-link-list a {{
        color: #93c5fd;
      }}
      .season-results-status {{
        color: #94a3b8;
      }}
      .match-result {{
        color: #5eead4;
      }}
      .match-meta {{
        color: #cbd5f5;
      }}
      .transfer-line {{
        color: #dbeafe;
      }}
      .news-meta {{
        color: #9ca3af;
      }}
      .transfer-category {{
        color: #bfdbfe;
      }}
      .roster-number {{
        background: #155e75;
        color: #ecfeff;
      }}
      .roster-official .roster-number {{
        background: #1f2933;
      }}
      .roster-details {{
        color: #cbd5f5;
      }}
      .update-note {{
        background: rgba(15, 118, 110, 0.16);
        color: #ccfbf1;
        border-color: rgba(45, 212, 191, 0.35);
      }}
      .notice-list li {{
        background: linear-gradient(135deg, #7c2d12, #a16207);
        color: #fef3c7;
        box-shadow: 0 20px 48px rgba(250, 204, 21, 0.35);
      }}
      .team-photo figcaption {{
        color: #94a3b8;
      }}
      a {{
        color: #5eead4;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>Nächster USC-Heimgegner:<br><span data-next-opponent>{escape(heading)}</span></h1>
    <div class=\"meta\">
      {meta_html}
    </div>
{notes_html}
    <section>
      <h2>Spiele: {escape(heading)}</h2>
      <ul class=\"match-list\">
        {opponent_items}
      </ul>
    </section>
    <section>
      <h2>Spiele: {escape(USC_CANONICAL_NAME)}</h2>
      <ul class=\"match-list\">
        {usc_items}
      </ul>
    </section>
    <section class=\"lineup-link\">
      <ul>
        {lineup_link_items}
      </ul>
    </section>
    <section class=\"roster-group\">
      <details class=\"accordion\">
        <summary>Kader {escape(heading)}</summary>
        <div class=\"accordion-content\">
{opponent_photo_block}          <ul class=\"roster-list\">
            {opponent_roster_items}
          </ul>
        </div>
      </details>
      <details class=\"accordion\">
        <summary>Kader {escape(USC_CANONICAL_NAME)}</summary>
        <div class=\"accordion-content\">
{usc_photo_block}          <ul class=\"roster-list\">
            {usc_roster_items}
          </ul>
        </div>
      </details>
    </section>
    <section class=\"transfer-group\">
      <details class=\"accordion\">
        <summary>Wechselbörse {escape(heading)}</summary>
        <div class=\"accordion-content\">
          <ul class=\"transfer-list\">
            {opponent_transfer_items}
          </ul>
        </div>
      </details>
      <details class=\"accordion\">
        <summary>Wechselbörse {escape(USC_CANONICAL_NAME)}</summary>
        <div class=\"accordion-content\">
          <ul class=\"transfer-list\">
            {usc_transfer_items}
          </ul>
        </div>
      </details>
    </section>
    <section class=\"news-group\">
      <details class=\"accordion\">
        <summary>News von {escape(heading)}</summary>
        <div class=\"accordion-content\">
          <ul class=\"news-list\">
            {opponent_news_items}
          </ul>
        </div>
      </details>
      <details class=\"accordion\">
        <summary>News von {escape(USC_CANONICAL_NAME)}</summary>
        <div class=\"accordion-content\">
          <ul class=\"news-list\">
            {usc_news_items}
          </ul>
        </div>
      </details>
    </section>
{mvp_section_html}    <section class=\"instagram-group\">
      <h2>Instagram-Links</h2>
      <div class=\"instagram-grid\">
        <article class=\"instagram-card\">
          <h3>{escape(heading)}</h3>
          <ul class=\"instagram-list\">
            {opponent_instagram_items}
          </ul>
        </article>
        <article class=\"instagram-card\">
          <h3>{escape(USC_CANONICAL_NAME)}</h3>
          <ul class=\"instagram-list\">
            {usc_instagram_items}
          </ul>
        </article>
      </div>
    </section>
{season_results_section}
{update_note_html}
  </main>
</body>
</html>
"""

    return html


__all__ = [
    "BERLIN_TZ",
    "DEFAULT_SCHEDULE_URL",
    "NEWS_LOOKBACK_DAYS",
    "NewsItem",
    "Match",
    "MatchResult",
    "RosterMember",
    "MatchStatsTotals",
    "TransferItem",
    "TEAM_HOMEPAGES",
    "TEAM_ROSTER_IDS",
    "TABLE_URL",
    "VBL_NEWS_URL",
    "VBL_PRESS_URL",
    "WECHSELBOERSE_URL",
    "USC_HOMEPAGE",
    "collect_team_news",
    "collect_team_transfers",
    "collect_match_stats_totals",
    "collect_instagram_links",
    "collect_team_roster",
    "collect_team_photo",
    "build_html_report",
    "download_schedule",
    "get_team_homepage",
    "get_team_roster_url",
    "fetch_team_news",
    "fetch_schedule",
    "find_last_matches_for_team",
    "find_next_match_for_team",
    "find_next_usc_home_match",
    "load_schedule_from_file",
    "parse_roster",
    "parse_schedule",
]
