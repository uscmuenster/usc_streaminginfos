from __future__ import annotations

import base64
import csv
import time
from dataclasses import dataclass, replace
import re
from datetime import date, datetime, timedelta
from pathlib import Path
import mimetypes
import sys
from html import escape, unescape
from io import BytesIO, StringIO
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo
from urllib.parse import parse_qs, urljoin, urlparse
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET
from textwrap import indent

from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadError

import requests
from bs4 import BeautifulSoup, Tag

from .broadcast_plan import (
    BROADCAST_PLAN,
    REFERENCE_KICKOFF_TIME,
)
from .broadcast_satzpause12 import BROADCAST_PLAN as FIRST_SET_BREAK_PLAN
from .broadcast_satzpause23 import BROADCAST_PLAN as SECOND_SET_BREAK_PLAN
from .broadcast_spielende import BROADCAST_PLAN as POST_MATCH_PLAN

DEFAULT_SCHEDULE_URL = "https://www.volleyball-bundesliga.de/servlet/league/PlayingScheduleCsvExport?matchSeriesId=776311171"
DVV_POKAL_SCHEDULE_URL = "https://www.dvv-pokal.de/servlet/league/PlayingScheduleCsvExport?matchSeriesId=776311591"
DEFAULT_ADDITIONAL_SCHEDULE_URLS: Tuple[str, ...] = (DVV_POKAL_SCHEDULE_URL,)
SCHEDULE_COMPETITION_LABELS: Dict[str, str] = {
    DEFAULT_SCHEDULE_URL: "VBL",
    DVV_POKAL_SCHEDULE_URL: "DVV-Pokal",
}
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
BERLIN_TIMEZONE_NAME = "Europe/Berlin"
BERLIN_TZ = ZoneInfo(BERLIN_TIMEZONE_NAME)
USC_CANONICAL_NAME = "USC Münster"
USC_HOMEPAGE = "https://www.usc-muenster.de/"
TEAM_LINKS_CSV_PATH = Path(__file__).with_name("team_links.csv")
_POSTAL_CODE_PREFIX_RE = re.compile(r"^\d{4,5}(?:[-/ ]\d{4,5})?\s+(?P<city>.+)$")

# Farbkonfiguration für Hervorhebungen von USC und Gegner.
# Werte können bei Bedarf angepasst werden, um die farbliche Darstellung global zu ändern.
HIGHLIGHT_COLORS: Dict[str, Dict[str, str]] = {
    "usc": {
        "row_bg": "#dcfce7",
        "row_text": "#047857",
        "legend_dot": "#16a34a",
        "accordion_bg": "#dcfce7",
        "accordion_shadow": "rgba(22, 163, 74, 0.08)",
        "card_border": "rgba(45, 212, 191, 0.55)",
        "card_shadow": "rgba(45, 212, 191, 0.16)",
        "mvp_bg": "rgba(16, 185, 129, 0.12)",
        "mvp_border": "rgba(5, 150, 105, 0.24)",
        "mvp_score": "#047857",
        "dark_row_bg": "rgba(22, 163, 74, 0.25)",
        "dark_row_text": "#bbf7d0",
        "dark_accordion_bg": "#1a4f3a",
        "dark_accordion_shadow": "rgba(74, 222, 128, 0.26)",
    },
    "opponent": {
        "row_bg": "#e0f2fe",
        "row_text": "#1d4ed8",
        "legend_dot": "#2563eb",
        "accordion_bg": "#e0f2fe",
        "accordion_shadow": "rgba(30, 64, 175, 0.08)",
        "card_border": "rgba(59, 130, 246, 0.35)",
        "card_shadow": "rgba(59, 130, 246, 0.18)",
        "mvp_bg": "rgba(59, 130, 246, 0.12)",
        "mvp_border": "rgba(37, 99, 235, 0.22)",
        "mvp_score": "#1d4ed8",
        "dark_row_bg": "rgba(59, 130, 246, 0.18)",
        "dark_row_text": "#bfdbfe",
        "dark_accordion_bg": "#1c3f5f",
        "dark_accordion_shadow": "rgba(56, 189, 248, 0.28)",
    },
}

THEME_COLORS: Dict[str, str] = {
    "mvp_overview_summary_bg": "#0f766e",
    "dark_mvp_overview_summary_bg": "rgba(253, 186, 116, 0.35)",
}

INTERNATIONAL_MATCHES_LINK: tuple[str, str] = (
    "internationale_spiele.html",
    "Internationale Spiele 2025/26",
)

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
    competition: Optional[str] = None

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
class DirectComparisonSummary:
    matches_played: int
    usc_wins: int
    opponent_wins: int
    usc_sets_for: int
    opponent_sets_for: int
    usc_points_for: int
    opponent_points_for: int

    @property
    def usc_losses(self) -> int:
        return self.opponent_wins

    @property
    def opponent_losses(self) -> int:
        return self.usc_wins

    @property
    def usc_win_pct(self) -> Optional[float]:
        if self.matches_played <= 0:
            return None
        return (self.usc_wins / self.matches_played) * 100

    @property
    def opponent_win_pct(self) -> Optional[float]:
        if self.matches_played <= 0:
            return None
        return (self.opponent_wins / self.matches_played) * 100


@dataclass(frozen=True)
class DirectComparisonMatch:
    match_id: Optional[str]
    date: Optional[date]
    date_label: Optional[str]
    season: Optional[str]
    home_team: str
    away_team: str
    round_label: Optional[str]
    competition: Optional[str]
    location: Optional[str]
    result_sets: Optional[str]
    result_points: Optional[str]
    set_scores: Tuple[str, ...]
    usc_sets: Optional[int]
    opponent_sets: Optional[int]
    usc_points: Optional[int]
    opponent_points: Optional[int]
    usc_won: Optional[bool]


@dataclass(frozen=True)
class DirectComparisonData:
    summary: DirectComparisonSummary
    matches: Tuple[DirectComparisonMatch, ...]
    seasons: Tuple[str, ...]


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


def _normalize_competition_label(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    normalized = cleaned.replace("1. Bundesliga Frauen", "VBL")
    normalized = re.sub(r"\s{2,}", " ", normalized).strip()
    return normalized or None


def _strip_postal_code_prefix(text: str) -> str:
    match = _POSTAL_CODE_PREFIX_RE.match(text)
    if match:
        return match.group("city").strip()
    return text.strip()


def _normalize_direct_comparison_location(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None

    trailing = cleaned.rstrip()
    city_candidate: Optional[str] = None
    if trailing.endswith(")"):
        start = trailing.rfind("(")
        if start != -1:
            inner = trailing[start + 1 : -1].strip()
            if inner:
                stripped_city = _strip_postal_code_prefix(inner)
                if stripped_city:
                    city_candidate = stripped_city
        trailing = trailing[:start].rstrip() if start != -1 else trailing
        if city_candidate:
            return city_candidate

    postal_stripped = _strip_postal_code_prefix(cleaned)
    if postal_stripped and postal_stripped != cleaned:
        return postal_stripped

    fallback = trailing.strip()
    if fallback:
        return fallback

    return None


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


def _resolve_schedule_urls(
    primary_url: Optional[str],
    extra_urls: Optional[Sequence[str]],
) -> List[str]:
    urls: List[str] = []
    if primary_url:
        urls.append(primary_url)
    if extra_urls:
        for entry in extra_urls:
            if entry:
                urls.append(entry)
    return urls


def _infer_competition_label(
    schedule_url: str,
    *,
    primary_url: Optional[str] = None,
) -> Optional[str]:
    label = SCHEDULE_COMPETITION_LABELS.get(schedule_url)
    if label:
        return label
    if primary_url and schedule_url == primary_url:
        return SCHEDULE_COMPETITION_LABELS.get(schedule_url)
    return None


def _deduplicate_matches(matches: Iterable[Match]) -> List[Match]:
    seen: set[tuple[datetime, str, str]] = set()
    index_lookup: Dict[tuple[datetime, str, str], int] = {}
    ordered = sorted(matches, key=lambda match: match.kickoff)
    unique: List[Match] = []
    for match in ordered:
        signature = (
            match.kickoff,
            normalize_name(match.home_team),
            normalize_name(match.away_team),
        )
        if signature in seen:
            existing_index = index_lookup[signature]
            existing_match = unique[existing_index]
            if not existing_match.competition and match.competition:
                unique[existing_index] = replace(
                    existing_match, competition=match.competition
                )
            continue
        seen.add(signature)
        index_lookup[signature] = len(unique)
        unique.append(match)
    return unique


def _combine_schedule_csv_texts(
    sources: Sequence[Tuple[str, Optional[str]]]
) -> str:
    rows: List[Dict[str, str]] = []
    fieldnames: List[str] = []
    seen_fieldnames: set[str] = set()

    def _ensure_field(name: str) -> None:
        if name not in seen_fieldnames:
            fieldnames.append(name)
            seen_fieldnames.add(name)

    for csv_text, competition_label in sources:
        buffer = StringIO(csv_text)
        reader = csv.DictReader(buffer, delimiter=";", quotechar="\"")
        if reader.fieldnames:
            for name in reader.fieldnames:
                _ensure_field(name)
        if competition_label:
            _ensure_field("Wettbewerb")
        for row in reader:
            if not any(value.strip() for value in row.values() if isinstance(value, str)):
                continue
            normalized_row = dict(row)
            if competition_label:
                existing_label = normalized_row.get("Wettbewerb")
                if not _normalize_schedule_field(existing_label):
                    normalized_row["Wettbewerb"] = competition_label
            elif "Wettbewerb" in normalized_row and _normalize_schedule_field(
                normalized_row.get("Wettbewerb")
            ):
                _ensure_field("Wettbewerb")
            rows.append(normalized_row)

    if not fieldnames:
        return ""

    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=fieldnames,
        delimiter=";",
        quotechar="\"",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        sanitized = {field: row.get(field, "") or "" for field in fieldnames}
        writer.writerow(sanitized)
    return output.getvalue()


def fetch_schedule(
    url: str = DEFAULT_SCHEDULE_URL,
    *,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> List[Match]:
    urls = _resolve_schedule_urls(url, DEFAULT_ADDITIONAL_SCHEDULE_URLS)
    matches: List[Match] = []
    for schedule_url in urls:
        try:
            csv_text = _download_schedule_text(
                schedule_url,
                retries=retries,
                delay_seconds=delay_seconds,
            )
        except Exception as exc:
            if schedule_url == url:
                raise
            print(
                f"Warnung: Zusätzlicher Spielplan konnte nicht geladen werden ({schedule_url}): {exc}",
                file=sys.stderr,
            )
            continue
        competition_label = _infer_competition_label(
            schedule_url, primary_url=url
        )
        matches.extend(parse_schedule(csv_text, competition=competition_label))
    return _deduplicate_matches(matches)


def download_schedule(
    destination: Path,
    *,
    url: str = DEFAULT_SCHEDULE_URL,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> Path:
    urls = _resolve_schedule_urls(url, DEFAULT_ADDITIONAL_SCHEDULE_URLS)
    csv_sources: List[Tuple[str, Optional[str]]] = []
    for schedule_url in urls:
        try:
            csv_text = _download_schedule_text(
                schedule_url,
                retries=retries,
                delay_seconds=delay_seconds,
            )
        except Exception as exc:
            if schedule_url == url:
                raise
            print(
                f"Warnung: Zusätzlicher Spielplan konnte nicht geladen werden ({schedule_url}): {exc}",
                file=sys.stderr,
            )
        else:
            competition_label = _infer_competition_label(
                schedule_url, primary_url=url
            )
            csv_sources.append((csv_text, competition_label))
    combined = _combine_schedule_csv_texts(csv_sources)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(combined, encoding="utf-8")
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


def load_schedule_from_file(
    path: Path, *, competition: Optional[str] = None
) -> List[Match]:
    csv_text = path.read_text(encoding="utf-8")
    return parse_schedule(csv_text, competition=competition)


def parse_schedule(
    csv_text: str,
    *,
    competition: Optional[str] = None,
) -> List[Match]:
    buffer = StringIO(csv_text)
    reader = csv.DictReader(buffer, delimiter=";", quotechar="\"")
    matches: List[Match] = []
    fallback_competition = _normalize_competition_label(competition)
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

        competition_field = _normalize_schedule_field(row.get("Wettbewerb"))
        match_competition = (
            _normalize_competition_label(competition_field) or fallback_competition
        )

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
                competition=match_competition,
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

    # Normalize HTML artefacts and unify separators that might appear in the
    # exported CSV. The VBL recently switched to including HTML line breaks and
    # HTML entities (e.g. ``&nbsp;``) in the referee column.  We also accept
    # common alternative separators such as ``|`` or newlines.
    normalized = unescape(value).replace("\xa0", " ")
    normalized = re.sub(r"<br\s*/?>", "\n", normalized, flags=re.IGNORECASE)

    parts = re.split(r"[\n;,/|]", normalized)
    referees: List[str] = []
    for part in parts:
        cleaned = part.strip(" \t-–·")
        cleaned = re.sub(
            r"^(?:\d+\.\s*)?(?:schiedsrichter(?:\*?in)?|sr)\s*:?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        if cleaned:
            referees.append(cleaned)

    return tuple(referees)


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
    replacements = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        "á": "a",
        "à": "a",
        "â": "a",
        "é": "e",
        "è": "e",
        "ê": "e",
        "í": "i",
        "ì": "i",
        "î": "i",
        "ó": "o",
        "ò": "o",
        "ô": "o",
        "ú": "u",
        "ù": "u",
        "û": "u",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    normalized = normalized.replace("muenster", "munster")
    normalized = normalized.replace("mnster", "munster")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _load_team_links_csv() -> List[Dict[str, str]]:
    if not TEAM_LINKS_CSV_PATH.exists():
        return []

    with TEAM_LINKS_CSV_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        entries: List[Dict[str, str]] = []
        for row in reader:
            team_name = (row.get("team_name") or "").strip()
            if not team_name:
                continue
            entries.append(
                {
                    "team_name": team_name,
                    "homepage_url": (row.get("homepage_url") or "").strip(),
                    "news_type": (row.get("news_type") or "").strip(),
                    "news_url": (row.get("news_url") or "").strip(),
                    "news_label": (row.get("news_label") or "").strip(),
                }
            )
    return entries


TEAM_LINKS_ROWS = _load_team_links_csv()


def slugify_team_name(value: str) -> str:
    simplified = simplify_text(value)
    slug = re.sub(r"[^a-z0-9]+", "-", simplified)
    return slug.strip("-")


def is_usc(name: str) -> bool:
    normalized = normalize_name(name)
    return "usc" in normalized and "munster" in normalized


def _build_team_homepages() -> Dict[str, str]:
    homepages: Dict[str, str] = {}
    for entry in TEAM_LINKS_ROWS:
        homepage = entry.get("homepage_url")
        if not homepage:
            continue
        normalized = normalize_name(entry["team_name"])
        if normalized:
            homepages[normalized] = homepage

    usc_key = normalize_name(USC_CANONICAL_NAME)
    if usc_key not in homepages:
        homepages[usc_key] = USC_HOMEPAGE

    return homepages


TEAM_HOMEPAGES = _build_team_homepages()


_MANUAL_STATS_TOTALS_DATA: Dict[str, Any] = {
    "matches": [
        {
            "stats_url": "https://www.volleyball-bundesliga.de/uploads/831866c1-9e16-46f8-827c-4b0dd011928b",
            "teams": [
                {
                    "name": "SSC Palmberg Schwerin",
                    "serve": {
                        "attempts": 74,
                        "errors": 6,
                        "points": 10,
                    },
                    "reception": {
                        "attempts": 37,
                        "errors": 3,
                        "positive_pct": "51%",
                        "perfect_pct": "24%",
                    },
                    "attack": {
                        "attempts": 78,
                        "errors": 10,
                        "blocked": 3,
                        "points": 37,
                        "success_pct": "47%",
                    },
                    "block": {
                        "points": 11,
                    },
                },
                {
                    "name": "ETV Hamburger Volksbank Volleys",
                    "aliases": [
                        "ETV Hamburger Volksbank V.",
                    ],
                    "serve": {
                        "attempts": 42,
                        "errors": 5,
                        "points": 3,
                    },
                    "reception": {
                        "attempts": 68,
                        "errors": 10,
                        "positive_pct": "29%",
                        "perfect_pct": "12%",
                    },
                    "attack": {
                        "attempts": 81,
                        "errors": 9,
                        "blocked": 11,
                        "points": 19,
                        "success_pct": "23%",
                    },
                    "block": {
                        "points": 3,
                    },
                },
            ],
        },
        {
            "stats_url": "https://www.volleyball-bundesliga.de/uploads/19bb6c96-f1cc-4867-9058-0864849ec964",
            "teams": [
                {
                    "name": "Binder Blaubären TSV Flacht",
                    "aliases": [
                        "Binder Blaubären Flacht",
                    ],
                    "serve": {
                        "attempts": 50,
                        "errors": 13,
                        "points": 2,
                    },
                    "reception": {
                        "attempts": 61,
                        "errors": 5,
                        "positive_pct": "21%",
                        "perfect_pct": "8%",
                    },
                    "attack": {
                        "attempts": 72,
                        "errors": 9,
                        "blocked": 7,
                        "points": 19,
                        "success_pct": "26%",
                    },
                    "block": {
                        "points": 6,
                    },
                },
                {
                    "name": "USC Münster",
                    "serve": {
                        "attempts": 74,
                        "errors": 13,
                        "points": 5,
                    },
                    "reception": {
                        "attempts": 37,
                        "errors": 2,
                        "positive_pct": "35%",
                        "perfect_pct": "14%",
                    },
                    "attack": {
                        "attempts": 82,
                        "errors": 7,
                        "blocked": 6,
                        "points": 40,
                        "success_pct": "49%",
                    },
                    "block": {
                        "points": 7,
                    },
                },
            ],
        },
    ],
}


_MANUAL_STATS_TOTALS: Optional[
    Dict[str, List[Tuple[Tuple[str, ...], str, MatchStatsMetrics]]]
] = None


def _load_manual_stats_totals() -> Dict[str, List[Tuple[Tuple[str, ...], str, MatchStatsMetrics]]]:
    global _MANUAL_STATS_TOTALS
    if _MANUAL_STATS_TOTALS is not None:
        return _MANUAL_STATS_TOTALS

    payload = _MANUAL_STATS_TOTALS_DATA
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
        "Binder Blaubären TSV Flacht": (
            "Binder Blaubären",
            "TSV Flacht",
            "Binder Blaubären Flacht",
        ),
        "Dresdner SC": ("DSC Volleys",),
        "ETV Hamburger Volksbank Volleys": (
            "ETV Hamburg",
            "Hamburg Volleys",
            "ETV Hamburger Volksbank V.",
        ),
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


def _build_team_short_name_lookup() -> Dict[str, str]:
    lookup: Dict[str, str] = dict(TEAM_SHORT_NAMES)
    for canonical, synonyms in TEAM_KEYWORD_SYNONYMS.items():
        short = TEAM_SHORT_NAMES.get(canonical)
        if not short:
            continue
        for alias in synonyms:
            lookup[normalize_name(alias)] = short
    return lookup


TEAM_SHORT_NAME_LOOKUP = _build_team_short_name_lookup()


TEAM_CANONICAL_NAMES: Mapping[str, str] = {
    normalize_name("Allianz MTV Stuttgart"): "Allianz MTV Stuttgart",
    normalize_name("Binder Blaubären TSV Flacht"): "Binder Blaubären TSV Flacht",
    normalize_name("Dresdner SC"): "Dresdner SC",
    normalize_name("ETV Hamburger Volksbank Volleys"): "ETV Hamburger Volksbank Volleys",
    normalize_name("Ladies in Black Aachen"): "Ladies in Black Aachen",
    normalize_name("SSC Palmberg Schwerin"): "SSC Palmberg Schwerin",
    normalize_name("Schwarz-Weiß Erfurt"): "Schwarz-Weiß Erfurt",
    normalize_name("Skurios Volleys Borken"): "Skurios Volleys Borken",
    normalize_name("USC Münster"): USC_CANONICAL_NAME,
    normalize_name("VC Wiesbaden"): "VC Wiesbaden",
    normalize_name("VfB Suhl LOTTO Thüringen"): "VfB Suhl LOTTO Thüringen",
}


def _build_team_canonical_lookup() -> Dict[str, str]:
    lookup: Dict[str, str] = dict(TEAM_CANONICAL_NAMES)
    for normalized_name, synonyms in TEAM_KEYWORD_SYNONYMS.items():
        canonical = TEAM_CANONICAL_NAMES.get(normalized_name)
        if not canonical:
            continue
        for alias in synonyms:
            lookup[normalize_name(alias)] = canonical
    for normalized_name, short_label in TEAM_SHORT_NAMES.items():
        canonical = TEAM_CANONICAL_NAMES.get(normalized_name)
        if not canonical:
            continue
        lookup[normalize_name(short_label)] = canonical
    return lookup


TEAM_CANONICAL_LOOKUP = _build_team_canonical_lookup()


def get_team_keywords(team_name: str) -> KeywordSet:
    synonyms = TEAM_KEYWORD_SYNONYMS.get(normalize_name(team_name), ())
    return build_keywords(team_name, *synonyms)


def _build_team_news_config() -> Dict[str, Dict[str, str]]:
    config: Dict[str, Dict[str, str]] = {}
    for entry in TEAM_LINKS_ROWS:
        news_url = entry.get("news_url")
        if not news_url:
            continue
        normalized = normalize_name(entry["team_name"])
        news_type = entry.get("news_type") or "rss"
        news_label = entry.get("news_label") or f"Homepage {entry['team_name']}"
        config[normalized] = {
            "type": news_type,
            "url": news_url,
            "label": news_label,
        }
    return config


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
    stripped = re.sub(r"(\d+\+\d{1,2})(\d+)", r"\1 \2", stripped)
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
    normalized_line = _normalize_stats_totals_line(line)
    match = _MATCH_STATS_LINE_PATTERN.search(normalized_line)
    if not match:
        tokens = re.findall(r"\d+%|\d+\+\d+|\d+", normalized_line)
        if len(tokens) > 13 and "+" in tokens[1]:
            prefix, suffix = tokens[1].split("+", 1)
            if suffix.isdigit() and len(suffix) == 1 and tokens[2].isdigit():
                tokens[1] = f"{tokens[1]}{tokens[2]}"
                tokens.pop(2)
        if len(tokens) < 13 or "+" not in tokens[1]:
            return None
        serve_split = _split_compound_value(tokens[3], first_max=60, second_max=60)
        attack_split = _split_compound_value(tokens[10], first_max=40, second_max=150)
        if not serve_split or not attack_split:
            return None
        try:
            return MatchStatsMetrics(
                serves_attempts=int(tokens[2]),
                serves_errors=serve_split[0],
                serves_points=serve_split[1],
                receptions_attempts=int(tokens[4]),
                receptions_errors=int(tokens[5]),
                receptions_positive_pct=tokens[6],
                receptions_perfect_pct=tokens[7],
                attacks_attempts=int(tokens[8]),
                attacks_errors=int(tokens[9]),
                attacks_blocked=attack_split[0],
                attacks_points=attack_split[1],
                attacks_success_pct=tokens[11],
                blocks_points=int(tokens[12]),
            )
        except ValueError:
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


def _coerce_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _coerce_optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    try:
        text = str(value).strip()
    except (TypeError, ValueError):
        return None
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _resolve_with_fallback(summary_value: int, fallback_value: int) -> int:
    if summary_value > 0:
        return summary_value
    if fallback_value > 0:
        return fallback_value
    return summary_value if summary_value >= 0 else 0


def prepare_direct_comparison(
    payload: Optional[Mapping[str, Any]], opponent_name: str
) -> Optional[DirectComparisonData]:
    if not payload or not opponent_name:
        return None

    seasons_raw = payload.get("seasons") if isinstance(payload, Mapping) else None
    if not isinstance(seasons_raw, Sequence):
        return None

    normalized_target = normalize_name(opponent_name)
    if not normalized_target:
        return None

    target_keywords = build_keywords(opponent_name)

    summary_totals = {
        "matches_played": 0,
        "usc_wins": 0,
        "opponent_wins": 0,
        "usc_sets_for": 0,
        "opponent_sets_for": 0,
        "usc_points_for": 0,
        "opponent_points_for": 0,
    }
    fallback_totals = {
        "matches_played": 0,
        "usc_wins": 0,
        "opponent_wins": 0,
        "usc_sets_for": 0,
        "opponent_sets_for": 0,
        "usc_points_for": 0,
        "opponent_points_for": 0,
    }

    matches: List[DirectComparisonMatch] = []
    seasons_collected: List[str] = []
    seen_seasons: set[str] = set()
    seen_matches: set[Tuple[Optional[str], Optional[date], str, str]] = set()

    for season_entry in seasons_raw:
        if not isinstance(season_entry, Mapping):
            continue
        season_label = str(season_entry.get("season") or "").strip() or None
        opponents = season_entry.get("opponents")
        if not isinstance(opponents, Sequence):
            continue
        for opponent_entry in opponents:
            if not isinstance(opponent_entry, Mapping):
                continue
            opponent_label = str(opponent_entry.get("team") or "").strip()
            if not opponent_label:
                continue
            opponent_normalized = normalize_name(opponent_label)
            if opponent_normalized != normalized_target:
                candidate_keywords = build_keywords(opponent_label)
                has_keyword_match = matches_keywords(opponent_label, target_keywords)
                reverse_keyword_match = matches_keywords(
                    opponent_name, candidate_keywords
                )
                if not has_keyword_match and not reverse_keyword_match:
                    continue
            if season_label and season_label not in seen_seasons:
                seasons_collected.append(season_label)
                seen_seasons.add(season_label)

            summary_payload = opponent_entry.get("summary")
            if isinstance(summary_payload, Mapping):
                summary_totals["matches_played"] += _coerce_int(
                    summary_payload.get("matches_played")
                )
                summary_totals["usc_wins"] += _coerce_int(summary_payload.get("usc_wins"))
                opponent_wins_value = summary_payload.get("opponent_wins")
                if opponent_wins_value is None:
                    opponent_wins_value = summary_payload.get("usc_losses")
                summary_totals["opponent_wins"] += _coerce_int(opponent_wins_value)
                summary_totals["usc_sets_for"] += _coerce_int(
                    summary_payload.get("usc_sets_for")
                )
                opponent_sets_value = summary_payload.get("opponent_sets_for")
                if opponent_sets_value is None:
                    opponent_sets_value = summary_payload.get("usc_sets_against")
                summary_totals["opponent_sets_for"] += _coerce_int(opponent_sets_value)
                summary_totals["usc_points_for"] += _coerce_int(
                    summary_payload.get("usc_points_for")
                )
                opponent_points_value = summary_payload.get("opponent_points_for")
                if opponent_points_value is None:
                    opponent_points_value = summary_payload.get("usc_points_against")
                summary_totals["opponent_points_for"] += _coerce_int(
                    opponent_points_value
                )

            matches_payload = opponent_entry.get("matches")
            if not isinstance(matches_payload, Sequence):
                continue
            for match_entry in matches_payload:
                if not isinstance(match_entry, Mapping):
                    continue
                match_id_raw = match_entry.get("match_id")
                match_id: Optional[str] = None
                if match_id_raw is not None:
                    match_id_candidate = str(match_id_raw).strip()
                    if match_id_candidate:
                        match_id = match_id_candidate

                date_raw = match_entry.get("date")
                if date_raw is not None:
                    date_candidate = str(date_raw).strip()
                    date_label = date_candidate or None
                else:
                    date_label = None
                parsed_date: Optional[date] = None
                if date_label:
                    try:
                        parsed_date = datetime.strptime(date_label, "%Y-%m-%d").date()
                    except ValueError:
                        parsed_date = None

                home_team_raw = match_entry.get("home_team")
                home_team = str(home_team_raw).strip() if home_team_raw else ""
                away_team_raw = match_entry.get("away_team")
                away_team = str(away_team_raw).strip() if away_team_raw else ""

                round_label = str(match_entry.get("round") or "").strip() or None
                competition = _normalize_competition_label(
                    match_entry.get("competition")
                )
                location_raw = str(match_entry.get("location") or "").strip()
                location = _normalize_direct_comparison_location(location_raw)

                result_payload = match_entry.get("result")
                result_sets: Optional[str] = None
                result_points: Optional[str] = None
                if isinstance(result_payload, Mapping):
                    result_sets = str(result_payload.get("sets") or "").strip() or None
                    result_points = str(result_payload.get("points") or "").strip() or None

                set_scores_field = match_entry.get("set_scores")
                set_scores: Tuple[str, ...] = ()
                if isinstance(set_scores_field, Sequence) and not isinstance(
                    set_scores_field, (str, bytes)
                ):
                    normalized_scores: List[str] = []
                    for score in set_scores_field:
                        try:
                            text = str(score)
                        except Exception:
                            continue
                        cleaned_score = text.strip()
                        if cleaned_score:
                            normalized_scores.append(cleaned_score)
                    if normalized_scores:
                        set_scores = tuple(normalized_scores)

                usc_sets_optional = _coerce_optional_int(match_entry.get("usc_sets"))
                opponent_sets_optional = _coerce_optional_int(
                    match_entry.get("opponent_sets")
                )
                usc_sets_value = usc_sets_optional if usc_sets_optional is not None else 0
                opponent_sets_value = (
                    opponent_sets_optional if opponent_sets_optional is not None else 0
                )
                usc_points_optional = _coerce_optional_int(match_entry.get("usc_points"))
                opponent_points_optional = _coerce_optional_int(
                    match_entry.get("opponent_points")
                )
                usc_points_value = (
                    usc_points_optional if usc_points_optional is not None else 0
                )
                opponent_points_value = (
                    opponent_points_optional
                    if opponent_points_optional is not None
                    else 0
                )

                fallback_totals["matches_played"] += 1
                fallback_totals["usc_sets_for"] += usc_sets_value
                fallback_totals["opponent_sets_for"] += opponent_sets_value
                if usc_points_optional is not None and opponent_points_optional is not None:
                    fallback_totals["usc_points_for"] += usc_points_optional
                    fallback_totals["opponent_points_for"] += opponent_points_optional

                usc_won_raw = match_entry.get("usc_won")
                usc_won: Optional[bool]
                if isinstance(usc_won_raw, bool):
                    usc_won = usc_won_raw
                elif isinstance(usc_won_raw, (int, float)):
                    usc_won = bool(usc_won_raw)
                elif isinstance(usc_won_raw, str):
                    lowered = usc_won_raw.strip().lower()
                    if lowered in {"true", "1", "ja", "sieg", "win"}:
                        usc_won = True
                    elif lowered in {"false", "0", "nein", "niederlage", "loss"}:
                        usc_won = False
                    else:
                        usc_won = None
                else:
                    usc_won = None

                if usc_won is True:
                    fallback_totals["usc_wins"] += 1
                elif usc_won is False:
                    fallback_totals["opponent_wins"] += 1
                else:
                    if usc_sets_value or opponent_sets_value:
                        if usc_sets_value > opponent_sets_value:
                            fallback_totals["usc_wins"] += 1
                            usc_won = True
                        elif opponent_sets_value > usc_sets_value:
                            fallback_totals["opponent_wins"] += 1
                            usc_won = False

                match_key = (
                    match_id,
                    parsed_date,
                    normalize_name(home_team) if home_team else "",
                    normalize_name(away_team) if away_team else "",
                )
                if match_key in seen_matches:
                    continue
                seen_matches.add(match_key)

                matches.append(
                    DirectComparisonMatch(
                        match_id=match_id,
                        date=parsed_date,
                        date_label=date_label,
                        season=season_label,
                        home_team=home_team or opponent_label,
                        away_team=away_team or USC_CANONICAL_NAME,
                        round_label=round_label,
                        competition=competition,
                        location=location,
                        result_sets=result_sets,
                        result_points=result_points,
                        set_scores=set_scores,
                        usc_sets=usc_sets_optional,
                        opponent_sets=opponent_sets_optional,
                        usc_points=usc_points_optional,
                        opponent_points=opponent_points_optional,
                        usc_won=usc_won,
                    )
                )

    matches_played = _resolve_with_fallback(
        summary_totals["matches_played"], fallback_totals["matches_played"]
    )
    usc_wins = _resolve_with_fallback(summary_totals["usc_wins"], fallback_totals["usc_wins"])
    opponent_wins = _resolve_with_fallback(
        summary_totals["opponent_wins"], fallback_totals["opponent_wins"]
    )
    usc_sets_for = _resolve_with_fallback(
        summary_totals["usc_sets_for"], fallback_totals["usc_sets_for"]
    )
    opponent_sets_for = _resolve_with_fallback(
        summary_totals["opponent_sets_for"], fallback_totals["opponent_sets_for"]
    )
    usc_points_for = _resolve_with_fallback(
        summary_totals["usc_points_for"], fallback_totals["usc_points_for"]
    )
    opponent_points_for = _resolve_with_fallback(
        summary_totals["opponent_points_for"], fallback_totals["opponent_points_for"]
    )

    if matches and matches_played < len(matches):
        matches_played = len(matches)

    if matches_played > 0 and usc_wins + opponent_wins < matches_played:
        opponent_wins = matches_played - usc_wins

    if (
        matches_played <= 0
        and usc_wins <= 0
        and opponent_wins <= 0
        and not matches
    ):
        return None

    summary = DirectComparisonSummary(
        matches_played=matches_played,
        usc_wins=usc_wins,
        opponent_wins=opponent_wins,
        usc_sets_for=usc_sets_for,
        opponent_sets_for=opponent_sets_for,
        usc_points_for=usc_points_for,
        opponent_points_for=opponent_points_for,
    )

    matches_sorted = sorted(
        matches,
        key=lambda item: (
            item.date or date.min,
            item.match_id or "",
            item.season or "",
        ),
        reverse=True,
    )

    return DirectComparisonData(
        summary=summary,
        matches=tuple(matches_sorted),
        seasons=tuple(seasons_collected),
    )


def pretty_name(name: str) -> str:
    if is_usc(name):
        return USC_CANONICAL_NAME
    canonical = TEAM_CANONICAL_LOOKUP.get(normalize_name(name))
    if canonical:
        return canonical
    return (
        name.replace("Mnster", "Münster")
        .replace("Munster", "Münster")
        .replace("Thringen", "Thüringen")
        .replace("Wei", "Weiß")
        .replace("wei", "weiß")
    )


def get_team_short_label(name: str) -> str:
    normalized = normalize_name(name)
    short = TEAM_SHORT_NAME_LOOKUP.get(normalized)
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
    highlight_teams: Optional[Mapping[str, str]] = None,
    list_item_classes: Optional[Iterable[str]] = None,
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
        extras_html = " · ".join(extras)
        links_html = " · ".join(links)
        parts: List[str] = []
        if extras_html:
            parts.append(extras_html)
        if links_html:
            if parts:
                parts.append("<br>" + links_html)
            else:
                parts.append(links_html)
        meta_html = f"<div class=\"match-meta\">{''.join(parts)}</div>"
    stats_html = ""
    class_attr = ""
    if list_item_classes:
        class_names = [cls.strip() for cls in list_item_classes if cls and cls.strip()]
        if class_names:
            class_attr = f" class=\"{' '.join(class_names)}\""

    header_suffix = ""
    if match.competition and not match.is_finished:
        header_suffix = f" ({escape(match.competition)})"

    segments: List[str] = [
        f"<li{class_attr}>",
        "  <div class=\"match-line\">",
        (
            "    <div class=\"match-header\">"
            f"<strong>{escape(kickoff_label)}</strong> – {escape(teams)}{header_suffix}</div>"
        ),
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


def format_direct_comparison_section(
    comparison: Optional[DirectComparisonData], opponent_name: str
) -> str:
    opponent_label = pretty_name(opponent_name)
    heading_slug = slugify_team_name(opponent_label) or "opponent"
    heading_id = f"direct-comparison-heading-{heading_slug}"
    fallback_html = (
        f'    <aside class="broadcast-box direct-comparison-box" aria-labelledby="{heading_id}">\n'
        '      <details class="broadcast-box__details">\n'
        '        <summary class="broadcast-box__summary">\n'
        f'          <span class="broadcast-box__summary-title" id="{heading_id}" role="heading" aria-level="2">Direkter Vergleich</span>\n'
        '          <span class="broadcast-box__summary-indicator" aria-hidden="true"></span>\n'
        '        </summary>\n'
        '        <div class="broadcast-box__content">\n'
        '          <p class="direct-comparison__fallback">Keine Daten zum direkten Vergleich verfügbar.</p>\n'
        '        </div>\n'
        '      </details>\n'
        '    </aside>'
    )

    if not comparison:
        return fallback_html

    summary = comparison.summary
    has_content = summary.matches_played > 0 or bool(comparison.matches)
    if not has_content:
        return fallback_html

    usc_label = USC_CANONICAL_NAME
    usc_normalized = normalize_name(usc_label)
    opponent_raw_name = opponent_name

    def _teams_line(match: DirectComparisonMatch) -> str:
        home_raw = match.home_team or opponent_raw_name
        away_raw = match.away_team or usc_label
        usc_is_home = normalize_name(home_raw) == usc_normalized if home_raw else False
        if usc_is_home:
            first_raw = home_raw
            second_raw = match.away_team or opponent_raw_name
        else:
            first_raw = match.away_team or usc_label
            second_raw = match.home_team or opponent_raw_name
        first_label = pretty_name(first_raw)
        second_label = pretty_name(second_raw)
        return f"{escape(first_label)} – {escape(second_label)}"

    def render_metric(label: str, usc_value: str, opponent_value: str) -> str:
        return "\n".join(
            [
                "          <div class=\"direct-comparison__metric\">",
                f"            <span class=\"direct-comparison__metric-label\">{escape(label)}</span>",
                "            <div class=\"direct-comparison__metric-score\">",
                f"              <span class=\"direct-comparison__metric-team direct-comparison__metric-team--usc\">{escape(usc_label)}</span>",
                f"              <span class=\"direct-comparison__metric-value\">{escape(usc_value)} – {escape(opponent_value)}</span>",
                f"              <span class=\"direct-comparison__metric-team direct-comparison__metric-team--opponent\">{escape(opponent_label)}</span>",
                "            </div>",
                "          </div>",
            ]
        )

    def _match_result_label(match: DirectComparisonMatch) -> str:
        sets_label: Optional[str] = None
        if match.usc_sets is not None and match.opponent_sets is not None:
            sets_label = f"{match.usc_sets}:{match.opponent_sets}"
        elif match.result_sets:
            sets_label = match.result_sets

        detail_label: Optional[str] = None
        if match.set_scores:
            detail_label = ", ".join(escape(score) for score in match.set_scores)
        elif match.usc_points is not None and match.opponent_points is not None:
            detail_label = f"{match.usc_points}:{match.opponent_points}"
        elif match.result_points:
            detail_label = escape(match.result_points)

        if sets_label and detail_label:
            return f"{escape(sets_label)} ({detail_label})"
        if sets_label:
            return escape(sets_label)
        if detail_label:
            return f"({detail_label})"
        return ""

    metrics_lines = [
        "          <div class=\"direct-comparison__metrics\">",
        render_metric("Siege", str(summary.usc_wins), str(summary.opponent_wins)),
        render_metric(
            "Sätze",
            f"{summary.usc_sets_for}",
            f"{summary.opponent_sets_for}",
        ),
        "          </div>",
    ]

    matches_block = ""
    if comparison.matches:
        match_rows: List[str] = []
        for match in comparison.matches:
            header_parts: List[str] = []
            if match.date:
                header_parts.append(match.date.strftime("%d.%m.%Y"))
            elif match.date_label:
                label = match.date_label.strip()
                if label:
                    try:
                        parsed_label = datetime.strptime(label, "%Y-%m-%d").date()
                    except ValueError:
                        header_parts.append(label)
                    else:
                        header_parts.append(parsed_label.strftime("%d.%m.%Y"))
            if match.competition:
                header_parts.append(match.competition)
            if match.round_label:
                header_parts.append(match.round_label)
            if match.location:
                header_parts.append(match.location)

            meta_line_raw = " · ".join(part for part in header_parts if part)
            meta_line = escape(meta_line_raw) if meta_line_raw else "–"

            teams_line = _teams_line(match)

            result_label = _match_result_label(match) or "–"

            result_class = " direct-comparison__result--neutral"
            if match.usc_won is True:
                result_class = " direct-comparison__result--win"
            elif match.usc_won is False:
                result_class = " direct-comparison__result--loss"

            match_rows.append(
                "\n".join(
                    [
                        "            <tr class=\"broadcast-row direct-comparison__match-row\">",
                        f"              <td class=\"broadcast-cell direct-comparison__cell direct-comparison__cell--meta\">{meta_line}</td>",
                        f"              <td class=\"broadcast-cell direct-comparison__cell direct-comparison__cell--teams\">{teams_line}</td>",
                        f"              <td class=\"broadcast-cell direct-comparison__cell direct-comparison__cell--result{result_class}\">{result_label}</td>",
                        "            </tr>",
                    ]
                )
            )

        if match_rows:
            matches_block = "\n".join(
                [
                    "          <h3 class=\"direct-comparison__matches-heading\">Alle Duelle</h3>",
                    "          <div class=\"broadcast-table-wrapper direct-comparison__matches-wrapper\">",
                    "            <table class=\"broadcast-table direct-comparison__matches-table\">",
                    "              <thead>",
                    "                <tr>",
                    "                  <th scope=\"col\" class=\"broadcast-heading direct-comparison__heading direct-comparison__heading--meta\">Datum &amp; Wettbewerb</th>",
                    "                  <th scope=\"col\" class=\"broadcast-heading direct-comparison__heading direct-comparison__heading--teams\">Begegnung</th>",
                    "                  <th scope=\"col\" class=\"broadcast-heading direct-comparison__heading direct-comparison__heading--result\">Ergebnis</th>",
                    "                </tr>",
                    "              </thead>",
                    "              <tbody>",
                    "\n".join(match_rows),
                    "              </tbody>",
                    "            </table>",
                    "          </div>",
                ]
            )

    seasons_note = ""
    if comparison.seasons:
        unique_seasons = list(dict.fromkeys(comparison.seasons))
        if unique_seasons:
            ordered_seasons = sorted(unique_seasons)
            if len(ordered_seasons) == 1:
                season_label = f"Saison {ordered_seasons[0]}"
            else:
                season_label = f"Saisons {ordered_seasons[0]} – {ordered_seasons[-1]}"
            seasons_note = (
                "          <p class=\"direct-comparison__note\">"
                f"Datenbasis: {escape(season_label)}"
                "</p>"
            )

    content_parts: List[str] = []
    content_parts.extend(metrics_lines)
    if matches_block:
        content_parts.append(matches_block)
    if seasons_note:
        content_parts.append(seasons_note)

    section_lines = [
        f"    <aside class=\"broadcast-box direct-comparison-box\" aria-labelledby=\"{heading_id}\">",
        "      <details class=\"broadcast-box__details\">",
        "        <summary class=\"broadcast-box__summary\">",
        f"          <span class=\"broadcast-box__summary-title\" id=\"{heading_id}\" role=\"heading\" aria-level=\"2\">Direkter Vergleich</span>",
        "          <span class=\"broadcast-box__summary-indicator\" aria-hidden=\"true\"></span>",
        "        </summary>",
        "        <div class=\"broadcast-box__content\">",
        "\n".join(content_parts) if content_parts else "",
        "        </div>",
        "      </details>",
        "    </aside>",
    ]

    return "\n".join(line for line in section_lines if line)

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

        def value_for(row: Sequence[str], header: str) -> str:
            index = header_index.get(header)
            if index is not None and index < len(row):
                return row[index].strip()
            return ""

        team_entries: Dict[str, List[Dict[str, str]]] = {"opponent": [], "usc": []}
        for row in rows:
            values: Dict[str, str] = {}
            for header, idx in header_index.items():
                if idx < len(row):
                    values[header] = row[idx]

            name_value = escape((values.get("Name") or value_for(row, "Name") or "–"))
            rank_value = escape((values.get("Rang") or value_for(row, "Rang") or "–"))
            team_raw = (
                (values.get("Mannschaft") or values.get("Team") or value_for(row, "Mannschaft"))
            ).strip()
            team_label = get_team_short_label(team_raw) if team_raw else ""
            position_raw = (values.get("Position") or value_for(row, "Position")).strip()
            sets_raw = (values.get("Sätze") or value_for(row, "Sätze")).strip()
            games_raw = (values.get("Spiele") or value_for(row, "Spiele")).strip()

            wert1_raw = (values.get("Wert1") or value_for(row, "Wert1")).strip()
            wertung_raw = (values.get("Wertung") or value_for(row, "Wertung")).strip()

            if wert1_raw and wertung_raw:
                score_value = f"{escape(wert1_raw)} | {escape(wertung_raw)}"
            else:
                metric_columns = ("Wert1", "Wert2", "Wert3", "Kennzahl", "Wertung")
                metric_values: List[str] = []
                for key in metric_columns:
                    raw_value = (values.get(key) or value_for(row, key)).strip()
                    if raw_value:
                        metric_values.append(escape(raw_value))

                if metric_values:
                    first_metric = metric_values[0]
                    last_metric = metric_values[-1]
                    if len(metric_values) == 1 or first_metric == last_metric:
                        score_value = first_metric
                    else:
                        score_value = f"{first_metric} | {last_metric}"
                else:
                    score_value = "–"

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
            if sets_raw:
                meta_parts.append(f"{escape(sets_raw)} Sätze")
            if games_raw:
                meta_parts.append(f"{escape(games_raw)} Spiele")
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
    link_items: List[str] = []
    if isinstance(links_raw, Sequence):
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

    internal_link_url, internal_link_label = INTERNATIONAL_MATCHES_LINK
    link_items.append(
        f"          <li><a href=\"{escape(internal_link_url)}\">{escape(internal_link_label)}</a></li>"
    )
    link_items.append(
        "          <li><a href=\"https://uscmuenster.github.io/scouting/index2.html\" rel=\"noopener\" target=\"_blank\">Scouting USC Münster</a></li>"
    )
    link_items.append(
        "          <li><a href=\"https://github.com/uscmuenster/usc_streaminginfos\" rel=\"noopener\" target=\"_blank\">GitHub Projekt - Streaminginfos</a></li>"
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
    usc_upcoming: Optional[Sequence[Match]] = None,
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
    direct_comparison: Optional[DirectComparisonData] = None,
) -> str:
    heading = pretty_name(next_home.away_team)
    kickoff_raw = next_home.kickoff
    if kickoff_raw.tzinfo is None:
        kickoff_raw = kickoff_raw.replace(tzinfo=BERLIN_TZ)

    kickoff_dt = kickoff_raw.astimezone(BERLIN_TZ)
    kickoff_date = kickoff_dt.strftime("%d.%m.%Y")
    kickoff_weekday = GERMAN_WEEKDAYS.get(
        kickoff_dt.weekday(), kickoff_dt.strftime("%a")
    )
    kickoff_time = kickoff_dt.strftime("%H:%M")
    kickoff = f"{kickoff_date} ({kickoff_weekday}) {kickoff_time}"
    kickoff_label = f"{kickoff} Uhr"
    countdown_iso = kickoff_dt.isoformat(timespec="seconds")
    match_day = kickoff_dt.date()
    location = pretty_name(next_home.location)
    usc_url = get_team_homepage(USC_CANONICAL_NAME) or USC_HOMEPAGE
    opponent_url = get_team_homepage(next_home.away_team)

    def _combine_matches(
        upcoming_matches: Optional[Sequence[Match]],
        recent_matches: List[Match],
        highlight_lookup: Mapping[str, str],
    ) -> str:
        combined: List[str] = []
        seen: set[tuple[datetime, str, str]] = set()

        ordered: List[Match] = []
        next_match: Optional[Match] = None
        if upcoming_matches:
            upcoming_sorted = sorted(
                upcoming_matches,
                key=lambda match: match.kickoff,
            )
            ordered.extend(upcoming_sorted)
            next_match = upcoming_sorted[0]
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
            item_classes: List[str] = ["match-item"]
            if not match.is_finished:
                item_classes.append("match-item--upcoming")
                if next_match and match is next_match:
                    item_classes.append("match-item--next")
            else:
                item_classes.append("match-item--finished")
            combined.append(
                format_match_line(
                    match,
                    stats=stats_payload,
                    highlight_teams=highlight_lookup,
                    list_item_classes=item_classes,
                )
            )

        if not combined:
            return "<li>Keine Daten verfügbar.</li>"
        return "\n      ".join(combined)

    highlight_targets = {
        "usc": USC_CANONICAL_NAME,
        "opponent": next_home.away_team,
    }

    usc_items = _combine_matches(usc_upcoming, usc_recent, highlight_targets)
    opponent_upcoming: Optional[Sequence[Match]] = (
        (opponent_next,)
        if opponent_next
        else None
    )
    opponent_items = _combine_matches(
        opponent_upcoming,
        opponent_recent,
        highlight_targets,
    )

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
    direct_comparison_html = format_direct_comparison_section(
        direct_comparison,
        next_home.away_team,
    )

    navigation_links = [
        ("aufstellungen.html", "Startaufstellungen der letzten Begegnungen"),
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
    countdown_summary_html = "\n".join(
        [
            (
                "      <span class=\"countdown-banner\" data-countdown-banner "
                f"data-kickoff=\"{escape(countdown_iso)}\" "
                f"data-timezone=\"{escape(BERLIN_TIMEZONE_NAME)}\">"
            ),
            "        <span class=\"countdown-heading\" data-countdown-heading></span>",
            (
                "        <span class=\"countdown-display\" data-countdown-display"
                " aria-live=\"polite\">--:--:--</span>"
            ),
            "      </span>",
        ]
    )

    countdown_meta_lines = [
        (
            "<p class=\"countdown-meta__kickoff\">"
            f"<strong>Spieltermin:</strong> {escape(kickoff_label)}"
            "</p>"
        ),
        (
            "<p class=\"countdown-meta__location\">"
            f"<strong>Austragungsort:</strong> {escape(location)}"
            "</p>"
        ),
    ]

    if next_home.competition:
        countdown_meta_lines.append(
            (
                "<p class=\"countdown-meta__competition\">"
                f"<strong>Wettbewerb:</strong> {escape(next_home.competition)}"
                "</p>"
            )
        )

    countdown_meta_html = "\n".join(
        [
            "    <div class=\"countdown-meta\">",
            *[f"      {line}" for line in countdown_meta_lines],
            "    </div>",
        ]
    )

    meta_lines = []

    referees = list(next_home.referees)
    for idx in range(1, 3):
        if idx <= len(referees):
            referee_name = referees[idx - 1]
        else:
            referee_name = "noch nicht veröffentlicht"
        meta_lines.append(
            f"<p><strong>{idx}. Schiedsrichter*in:</strong> {escape(referee_name)}</p>"
        )

    meta_lines.append("<p class=\"meta-spacer\" aria-hidden=\"true\"></p>")
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

    def _format_minutes_seconds(delta: timedelta) -> str:
        total_seconds = int(round(delta.total_seconds()))
        total_seconds = max(total_seconds, 0)
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes:d}:{seconds:02d}"

    def _format_hms(delta: timedelta) -> str:
        total_seconds = int(round(delta.total_seconds()))
        total_seconds = abs(total_seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    tzinfo = kickoff_dt.tzinfo or BERLIN_TZ
    reference_dt = datetime.combine(kickoff_dt.date(), REFERENCE_KICKOFF_TIME)
    reference_dt = reference_dt.replace(tzinfo=tzinfo)

    broadcast_item_blocks: List[str] = []
    for entry in BROADCAST_PLAN:
        planned_dt = datetime.combine(kickoff_dt.date(), entry.planned_time)
        planned_dt = planned_dt.replace(tzinfo=tzinfo)
        offset = planned_dt - reference_dt
        actual_dt = kickoff_dt + offset
        countdown_delta = kickoff_dt - actual_dt
        if countdown_delta.total_seconds() >= 0:
            countdown_prefix = "\u2212"
            countdown_value = countdown_delta
        else:
            countdown_prefix = "+"
            countdown_value = -countdown_delta
        countdown_label = f"{countdown_prefix}{_format_minutes_seconds(countdown_value)}"
        actual_time_label = actual_dt.strftime("%H:%M:%S")
        duration_label = _format_hms(entry.duration)
        broadcast_item_blocks.append(
            "\n".join(
                [
                    "<tr class=\"broadcast-row\">",
                    f"  <th scope=\"row\" class=\"broadcast-cell broadcast-cell--time\">{escape(actual_time_label)} Uhr</th>",
                    f"  <td class=\"broadcast-cell broadcast-cell--countdown\">{escape(countdown_label)}</td>",
                    f"  <td class=\"broadcast-cell broadcast-cell--duration\">{escape(duration_label)}</td>",
                    f"  <td class=\"broadcast-cell broadcast-cell--note\">{escape(entry.note)}</td>",
                    "</tr>",
                ]
            )
        )

    broadcast_box_lines = [
        "<aside class=\"broadcast-box\" aria-labelledby=\"broadcast-plan-heading\">",
        "  <details class=\"broadcast-box__details\">",
        "    <summary class=\"broadcast-box__summary\">",
        (
            "      <span class=\"broadcast-box__summary-title\" "
            "id=\"broadcast-plan-heading\" role=\"heading\" "
            "aria-level=\"2\">Sendeablauf vor Spielbeginn</span>"
        ),
        *countdown_summary_html.splitlines(),
        "      <span class=\"broadcast-box__summary-indicator\" aria-hidden=\"true\"></span>",
        "    </summary>",
        "    <div class=\"broadcast-box__content\">",
    ]
    if broadcast_item_blocks:
        broadcast_box_lines.extend(
            [
                "      <div class=\"broadcast-table-wrapper\">",
                "        <table class=\"broadcast-table\">",
                "          <thead>",
                "            <tr>",
                "              <th scope=\"col\" class=\"broadcast-heading broadcast-heading--time\">Zeit</th>",
                "              <th scope=\"col\" class=\"broadcast-heading broadcast-heading--countdown\">Countdown</th>",
                "              <th scope=\"col\" class=\"broadcast-heading broadcast-heading--duration\">Dauer</th>",
                "              <th scope=\"col\" class=\"broadcast-heading broadcast-heading--note\">Programmpunkt</th>",
                "            </tr>",
                "          </thead>",
                "          <tbody>",
            ]
        )
        broadcast_box_lines.extend(indent(block, "            ") for block in broadcast_item_blocks)
        broadcast_box_lines.extend(
            [
                "          </tbody>",
                "        </table>",
                "      </div>",
            ]
        )
    else:
        broadcast_box_lines.append(
            "      <p class=\"broadcast-empty\">Keine Sendeplanung hinterlegt.</p>"
        )
    broadcast_box_lines.extend(
        [
            "    </div>",
            "  </details>",
            "</aside>",
        ]
    )
    broadcast_box_html = "\n".join(broadcast_box_lines)

    def _render_set_break_box(
        plan: Iterable[Any],
        heading_id: str,
        heading_label: str,
    ) -> str:
        rows: List[str] = []
        cumulative_duration = timedelta()
        for entry in plan:
            start_label = _format_minutes_seconds(cumulative_duration)
            duration_label = _format_minutes_seconds(entry.duration)
            rows.append(
                "\n".join(
                    [
                        "<tr class=\"broadcast-row\">",
                        f"  <td class=\"broadcast-cell broadcast-cell--start\">{escape(start_label)}</td>",
                        f"  <td class=\"broadcast-cell broadcast-cell--duration\">{escape(duration_label)}</td>",
                        f"  <td class=\"broadcast-cell broadcast-cell--note\">{escape(entry.note)}</td>",
                        "</tr>",
                    ]
                )
            )
            cumulative_duration += entry.duration

        heading_id_attr = escape(heading_id, quote=True)
        heading_label_html = escape(heading_label)

        box_lines = [
            f"<aside class=\"broadcast-box\" aria-labelledby=\"{heading_id_attr}\">",
            "  <details class=\"broadcast-box__details\">",
            "    <summary class=\"broadcast-box__summary\">",
            (
                "      <span class=\"broadcast-box__summary-title\" "
                f"id=\"{heading_id_attr}\" role=\"heading\" "
                f"aria-level=\"2\">{heading_label_html}</span>"
            ),
            "      <span class=\"broadcast-box__summary-indicator\" aria-hidden=\"true\"></span>",
            "    </summary>",
            "    <div class=\"broadcast-box__content\">",
        ]
        if rows:
            box_lines.extend(
                [
                    "      <div class=\"broadcast-table-wrapper\">",
                    "        <table class=\"broadcast-table\">",
                    "          <thead>",
                    "            <tr>",
                    "              <th scope=\"col\" class=\"broadcast-heading broadcast-heading--start\">Start</th>",
                    "              <th scope=\"col\" class=\"broadcast-heading broadcast-heading--duration\">Dauer</th>",
                    "              <th scope=\"col\" class=\"broadcast-heading broadcast-heading--note\">Programmpunkt</th>",
                    "            </tr>",
                    "          </thead>",
                    "          <tbody>",
                ]
            )
            box_lines.extend(indent(row, "            ") for row in rows)
            box_lines.extend(
                [
                    "          </tbody>",
                    "        </table>",
                    "      </div>",
                ]
            )
        else:
            box_lines.append(
                "      <p class=\"broadcast-empty\">Keine Informationen zur Satzpause hinterlegt.</p>"
            )
        box_lines.extend(
            [
                "    </div>",
                "  </details>",
                "</aside>",
            ]
        )
        return "\n".join(box_lines)

    set_break_12_box_html = _render_set_break_box(
        FIRST_SET_BREAK_PLAN,
        "set-break-1-2-heading",
        "Satzpause 1 → 2 | 3 → 4 | 4 → 5",
    )
    set_break_23_box_html = _render_set_break_box(
        SECOND_SET_BREAK_PLAN,
        "set-break-2-3-heading",
        "Satzpause 2 → 3",
    )
    post_match_box_html = _render_set_break_box(
        POST_MATCH_PLAN,
        "post-match-heading",
        "Spielende",
    )

    stopwatch_box_lines = [
        "<aside class=\"broadcast-box\" aria-labelledby=\"stopwatch-heading\">",
        "  <details class=\"broadcast-box__details\" data-stopwatch>",
        "    <summary class=\"broadcast-box__summary\">",
        (
            "      <span class=\"broadcast-box__summary-title\" "
            "id=\"stopwatch-heading\" role=\"heading\" "
            "aria-level=\"2\">Stoppuhr</span>"
        ),
        "      <span class=\"broadcast-box__summary-indicator\" aria-hidden=\"true\"></span>",
        "    </summary>",
        "    <div class=\"broadcast-box__content\">",
        "      <div class=\"stopwatch-display\" data-stopwatch-display aria-live=\"polite\">00:00</div>",
        "      <div class=\"stopwatch-controls\" role=\"group\" aria-label=\"Stoppuhr-Steuerung\">",
        "        <button type=\"button\" class=\"stopwatch-button\" data-stopwatch-start>Start</button>",
        "        <button type=\"button\" class=\"stopwatch-button\" data-stopwatch-stop>Stopp</button>",
        "        <button type=\"button\" class=\"stopwatch-button\" data-stopwatch-reset>Zurücksetzen</button>",
        "      </div>",
        "    </div>",
        "  </details>",
        "</aside>",
    ]
    stopwatch_box_html = "\n".join(stopwatch_box_lines)

    hero_secondary_lines = [
        "      <div class=\"hero-secondary\">",
        indent(broadcast_box_html, "        ").rstrip(),
        indent(set_break_12_box_html, "        ").rstrip(),
        indent(set_break_23_box_html, "        ").rstrip(),
        indent(post_match_box_html, "        ").rstrip(),
        "      </div>",
    ]
    hero_layout_lines = [
        "    <div class=\"hero-layout\">",
        "      <div class=\"hero-primary\">",
        indent(countdown_meta_html, "        ").rstrip(),
        "        <div class=\"meta\">",
        f"          {meta_html}",
        "        </div>",
        "        <div class=\"hero-stopwatch\">",
        indent(stopwatch_box_html, "          ").rstrip(),
        "        </div>",
        "      </div>",
        *hero_secondary_lines,
        "    </div>",
    ]
    hero_layout_html = "\n".join(hero_layout_lines)

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
  <meta http-equiv=\"Cache-Control\" content=\"no-cache, no-store, must-revalidate\">
  <meta http-equiv=\"Pragma\" content=\"no-cache\">
  <meta http-equiv=\"Expires\" content=\"0\">
  <meta name=\"theme-color\" content=\"{THEME_COLORS['mvp_overview_summary_bg']}\">
  <link rel=\"icon\" type=\"image/png\" sizes=\"32x32\" href=\"favicon.png\">
  <link rel=\"icon\" type=\"image/png\" sizes=\"192x192\" href=\"favicon.png\">
  <link rel=\"apple-touch-icon\" href=\"favicon.png\">
  <link rel=\"manifest\" href=\"manifest.webmanifest\">
  <title>Nächster USC-Heimgegner</title>
  <style>
    :root {{
      color-scheme: light dark;
      --font-scale: {scale_value};
      --font-context-scale: 1;
      --theme-color: {THEME_COLORS['mvp_overview_summary_bg']};
      --accordion-opponent-bg: {HIGHLIGHT_COLORS['opponent']['accordion_bg']};
      --accordion-opponent-shadow: {HIGHLIGHT_COLORS['opponent']['accordion_shadow']};
      --accordion-usc-bg: {HIGHLIGHT_COLORS['usc']['accordion_bg']};
      --accordion-usc-shadow: {HIGHLIGHT_COLORS['usc']['accordion_shadow']};
      --usc-highlight-row-bg: {HIGHLIGHT_COLORS['usc']['row_bg']};
      --usc-highlight-row-text: {HIGHLIGHT_COLORS['usc']['row_text']};
      --usc-highlight-card-border: {HIGHLIGHT_COLORS['usc']['card_border']};
      --usc-highlight-card-shadow: {HIGHLIGHT_COLORS['usc']['card_shadow']};
      --usc-highlight-mvp-bg: {HIGHLIGHT_COLORS['usc']['mvp_bg']};
      --usc-highlight-mvp-border: {HIGHLIGHT_COLORS['usc']['mvp_border']};
      --usc-highlight-mvp-score: {HIGHLIGHT_COLORS['usc']['mvp_score']};
      --usc-highlight-legend-dot: {HIGHLIGHT_COLORS['usc']['legend_dot']};
      --opponent-highlight-row-bg: {HIGHLIGHT_COLORS['opponent']['row_bg']};
      --opponent-highlight-row-text: {HIGHLIGHT_COLORS['opponent']['row_text']};
      --opponent-highlight-card-border: {HIGHLIGHT_COLORS['opponent']['card_border']};
      --opponent-highlight-card-shadow: {HIGHLIGHT_COLORS['opponent']['card_shadow']};
      --opponent-highlight-mvp-bg: {HIGHLIGHT_COLORS['opponent']['mvp_bg']};
      --opponent-highlight-mvp-border: {HIGHLIGHT_COLORS['opponent']['mvp_border']};
      --opponent-highlight-mvp-score: {HIGHLIGHT_COLORS['opponent']['mvp_score']};
      --opponent-highlight-legend-dot: {HIGHLIGHT_COLORS['opponent']['legend_dot']};
      --mvp-overview-summary-bg: {THEME_COLORS['mvp_overview_summary_bg']};
    }}
    @media (display-mode: standalone), (display-mode: fullscreen) {{
      :root {{
        --font-context-scale: 1.25;
      }}
    }}
    body {{
      margin: 0;
      font-family: \"Inter\", \"Segoe UI\", -apple-system, BlinkMacSystemFont, \"Helvetica Neue\", Arial, sans-serif;
      line-height: 1.6;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * clamp(0.95rem, 1.8vw, 1.05rem));
      background: #f5f7f9;
      color: #1f2933;
    }}
    main {{
      max-width: min(110rem, 96vw);
      margin: 0 auto;
      padding: clamp(0.6rem, 2.5vw, 1.2rem) clamp(0.9rem, 3vw, 2.4rem);
    }}
    h1 {{
      color: #004c54;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * clamp(1.55rem, 4.5vw, 2.35rem));
      margin: 0 0 1.25rem 0;
    }}
    h2 {{
      font-size: calc(var(--font-scale) * var(--font-context-scale) * clamp(1.15rem, 3.6vw, 1.6rem));
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
    .meta-spacer {{
      height: clamp(0.6rem, 2.2vw, 1.2rem);
    }}
    .hero-layout {{
      display: grid;
      gap: clamp(1rem, 3vw, 1.8rem);
      align-items: start;
      margin-bottom: clamp(1.1rem, 3vw, 1.6rem);
      grid-template-columns: minmax(0, clamp(20rem, 34vw, 28rem)) minmax(0, 1fr);
    }}
    .hero-primary {{
      display: grid;
      gap: clamp(0.8rem, 2.4vw, 1.3rem);
    }}
    .hero-stopwatch {{
      display: grid;
    }}
    .hero-secondary {{
      display: grid;
      gap: clamp(0.9rem, 2.6vw, 1.4rem);
      align-content: start;
    }}
    @media (max-width: 70rem) {{
      .hero-layout {{
        grid-template-columns: 1fr;
      }}
    }}
    .broadcast-box {{
      border-radius: 1rem;
      background: #ffffff;
      padding: clamp(0.75rem, 2.2vw, 1.15rem);
      box-shadow: 0 18px 40px rgba(15, 118, 110, 0.16);
      border: 1px solid rgba(15, 118, 110, 0.18);
      display: grid;
      gap: clamp(0.55rem, 1.8vw, 0.8rem);
    }}
    .broadcast-box__details {{
      display: grid;
      gap: clamp(0.75rem, 2.2vw, 1.1rem);
      margin: 0;
    }}
    .broadcast-box__summary {{
      display: flex;
      align-items: center;
      gap: clamp(0.45rem, 2vw, 1.2rem);
      margin: 0;
      padding: 0;
      cursor: pointer;
      list-style: none;
    }}
    .broadcast-box__summary::-webkit-details-marker {{
      display: none;
    }}
    .broadcast-box__summary:focus-visible {{
      outline: 3px solid rgba(14, 165, 233, 0.55);
      border-radius: 0.75rem;
      outline-offset: 2px;
    }}
    .broadcast-box__summary-title {{
      flex: 1 1 auto;
      min-width: 0;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * clamp(1.4rem, 3.8vw, 1.8rem));
      font-weight: 700;
      color: #0f172a;
    }}
    .broadcast-box__summary-indicator {{
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: clamp(1.5rem, 4vw, 1.8rem);
      height: clamp(1.5rem, 4vw, 1.8rem);
      border-radius: 999px;
      border: 2px solid rgba(15, 118, 110, 0.35);
      color: #0f766e;
      font-size: clamp(0.85rem, 2.2vw, 1rem);
      transition: transform 0.2s ease, border-color 0.2s ease;
    }}
    .broadcast-box__summary-indicator::before {{
      content: "▸";
    }}
    .broadcast-box__details[open] .broadcast-box__summary-indicator {{
      transform: rotate(90deg);
      border-color: rgba(15, 118, 110, 0.6);
    }}
    .broadcast-box__details[open] .broadcast-box__summary-indicator::before {{
      content: "▾";
    }}
    .broadcast-box__content {{
      display: grid;
      gap: clamp(0.75rem, 2vw, 1.1rem);
    }}
    .broadcast-box h2 {{
      margin: 0;
    }}
    .stopwatch-display {{
      font-family: "Fira Mono", "SFMono-Regular", Menlo, Consolas, monospace;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * clamp(1.75rem, 5vw, 2.2rem));
      font-weight: 700;
      color: #0f172a;
      text-align: center;
      padding: clamp(0.35rem, 1vw, 0.6rem);
      border-radius: 0.75rem;
      background: rgba(15, 118, 110, 0.08);
      border: 1px solid rgba(15, 118, 110, 0.15);
    }}
    .stopwatch--running .stopwatch-display {{
      background: linear-gradient(135deg, rgba(15, 118, 110, 0.18), rgba(14, 165, 233, 0.2));
      border-color: rgba(14, 165, 233, 0.4);
      box-shadow: 0 18px 36px rgba(14, 165, 233, 0.22);
    }}
    .stopwatch-controls {{
      display: flex;
      flex-wrap: wrap;
      gap: clamp(0.3rem, 1.5vw, 0.55rem);
      justify-content: center;
    }}
    .stopwatch-button {{
      font: inherit;
      font-weight: 600;
      padding: clamp(0.35rem, 1vw, 0.55rem) clamp(0.75rem, 2.5vw, 1.1rem);
      border-radius: 999px;
      border: none;
      cursor: pointer;
      color: #ffffff;
      background: linear-gradient(135deg, #0f766e, #0ea5e9);
      box-shadow: 0 14px 30px rgba(14, 165, 233, 0.25);
      transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease;
    }}
    .stopwatch-button:hover {{
      filter: brightness(1.05);
      box-shadow: 0 16px 34px rgba(14, 165, 233, 0.35);
    }}
    .stopwatch-button:active {{
      transform: translateY(1px) scale(0.99);
    }}
    .stopwatch-button:focus-visible {{
      outline: 3px solid rgba(14, 165, 233, 0.55);
      outline-offset: 2px;
    }}
    .broadcast-table-wrapper {{
      border-radius: 0.85rem;
      border: 1px solid #e2e8f0;
      background: #f8fafc;
      overflow-x: auto;
    }}
    .broadcast-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 1rem);
    }}
    .broadcast-table thead th {{
      text-align: left;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.68rem);
      color: #0f766e;
      padding: 0.45rem 0.65rem;
      background: rgba(15, 118, 110, 0.08);
      border-bottom: 1px solid rgba(148, 163, 184, 0.35);
    }}
    .broadcast-heading--countdown,
    .broadcast-heading--duration,
    .broadcast-heading--start {{
      text-align: left;
    }}
    .broadcast-heading--note {{
      width: 55%;
    }}
    .broadcast-table thead th:first-child {{
      border-top-left-radius: 0.85rem;
    }}
    .broadcast-table thead th:last-child {{
      border-top-right-radius: 0.85rem;
    }}
    .broadcast-table tbody th,
    .broadcast-table tbody td {{
      padding: 0.3rem 0.65rem;
      vertical-align: top;
      border-top: 1px solid rgba(148, 163, 184, 0.35);
      line-height: 1.3;
      text-align: left;
    }}
    .broadcast-table tbody tr:first-child th,
    .broadcast-table tbody tr:first-child td {{
      border-top: none;
    }}
    .broadcast-cell--time {{
      font-family: "Fira Mono", "SFMono-Regular", Menlo, Consolas, monospace;
      font-weight: 600;
      white-space: nowrap;
    }}
    .broadcast-cell--countdown {{
      font-weight: 700;
      color: #0f766e;
      white-space: nowrap;
      text-align: left;
    }}
    .broadcast-cell--note {{
      font-weight: 500;
      line-height: 1.35;
    }}
    .broadcast-cell--duration {{
      text-align: left;
      white-space: nowrap;
      font-family: "Fira Mono", "SFMono-Regular", Menlo, Consolas, monospace;
    }}
    .broadcast-cell--start {{
      font-family: "Fira Mono", "SFMono-Regular", Menlo, Consolas, monospace;
      white-space: nowrap;
    }}
    .broadcast-empty {{
      margin: 0;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.9rem);
      color: #475569;
    }}
    @media (min-width: 60rem) {{
      .hero-layout {{
        grid-template-columns: minmax(0, 0.35fr) minmax(0, 0.65fr);
      }}
    }}
    @media (max-width: 50rem) {{
      .hero-layout {{
        grid-template-columns: minmax(0, 1fr);
      }}
    }}
    .countdown-meta {{
      display: grid;
      gap: clamp(0.2rem, 1.2vw, 0.45rem);
      margin: 0 0 clamp(0.55rem, 2vw, 0.9rem) 0;
    }}
    .countdown-meta p {{
      margin: 0;
    }}
    .countdown-meta__kickoff {{
      font-size: calc(var(--font-scale) * var(--font-context-scale) * clamp(1.05rem, 3.4vw, 1.25rem));
      font-weight: 600;
    }}
    .countdown-meta__location {{
      font-size: calc(var(--font-scale) * var(--font-context-scale) * clamp(0.95rem, 3vw, 1.1rem));
      font-weight: 500;
    }}
    .countdown-meta__competition {{
      font-size: calc(var(--font-scale) * var(--font-context-scale) * clamp(0.9rem, 2.6vw, 1.05rem));
      font-weight: 500;
    }}
    .countdown-banner {{
      margin: 0;
      padding: clamp(0.55rem, 1.7vw, 0.15rem) clamp(0.65rem, 2.2vw, 1.15rem);
      border-radius: 0.95rem;
      background: linear-gradient(135deg, #0f766e, #10b981);
      color: #f0fdf4;
      display: inline-flex;
      align-items: center;
      gap: clamp(0.35rem, 1.5vw, 0.6rem);
      width: auto;
      max-width: 100%;
    }}
    .countdown-banner--live {{
      background: linear-gradient(135deg, #b91c1c, #f97316);
      box-shadow: 0 18px 40px rgba(180, 83, 9, 0.4);
    }}
    .countdown-heading {{
      margin: 0;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 700;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * clamp(0.5rem, 1.5vw, 0.65rem));
    }}
    .countdown-display {{
      margin: 0;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * clamp(1.2rem, 3.6vw, 1.6rem));
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }}
    .update-note {{
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      padding: 0.25rem 0.6rem;
      background: #ecfdf5;
      color: #047857;
      border-radius: 999px;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.7rem);
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
      grid-template-columns: 1fr;
    }}
    @media (min-width: 48rem) {{
      .match-list {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .match-list li.match-item--upcoming {{
        grid-column: 1 / -1;
      }}
    }}
    .match-list li {{
      background: #ffffff;
      border-radius: 0.8rem;
      padding: 0.85rem clamp(0.9rem, 2.6vw, 1.3rem);
      box-shadow: 0 10px 30px rgba(0, 76, 84, 0.08);
    }}
    .direct-comparison-box {{
      margin-top: clamp(1rem, 3vw, 1.75rem);
    }}
    .direct-comparison__metrics {{
      display: grid;
      gap: clamp(0.6rem, 2.5vw, 0.85rem);
      grid-template-columns: repeat(auto-fit, minmax(min(14rem, 100%), 1fr));
      margin: 0 0 clamp(0.85rem, 3vw, 1.15rem);
    }}
    .direct-comparison__metric {{
      background: rgba(15, 118, 110, 0.08);
      border-radius: 0.85rem;
      padding: clamp(0.6rem, 2.2vw, 0.95rem);
      display: grid;
      gap: clamp(0.35rem, 1.6vw, 0.55rem);
    }}
    .direct-comparison__metric-label {{
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.72rem);
      color: #0f766e;
      text-align: center;
      margin: 0;
    }}
    .direct-comparison__metric-score {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
      gap: clamp(0.35rem, 1.2vw, 0.6rem);
      align-items: baseline;
      justify-items: center;
    }}
    .direct-comparison__metric-team {{
      font-weight: 600;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 1.4rem);
      color: #0f172a;
      text-align: center;
    }}
    .direct-comparison__metric-team--usc {{
      color: {HIGHLIGHT_COLORS['usc']['row_text']};
    }}
    .direct-comparison__metric-team--opponent {{
      color: {HIGHLIGHT_COLORS['opponent']['row_text']};
    }}
    .direct-comparison__metric-value {{
      font-weight: 700;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 1.05rem);
      font-variant-numeric: tabular-nums;
      color: #0f766e;
    }}
    .direct-comparison__last-meeting {{
      background: rgba(15, 118, 110, 0.06);
      border-radius: 0.9rem;
      padding: clamp(0.7rem, 2.2vw, 1.05rem);
      display: grid;
      gap: clamp(0.35rem, 1.2vw, 0.6rem);
      margin-bottom: clamp(0.85rem, 3vw, 1.2rem);
    }}
    .direct-comparison__last-meeting h3 {{
      margin: 0;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 1.05rem);
    }}
    .direct-comparison__last-teams {{
      margin: 0;
      font-weight: 700;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 1rem);
    }}
    .direct-comparison__last-meta {{
      margin: 0;
      color: #1f2937;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.85rem);
    }}
    .direct-comparison__last-result {{
      margin: 0;
      font-weight: 700;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.95rem);
    }}
    .direct-comparison__matches-heading {{
      margin: 0 0 clamp(0.5rem, 2vw, 0.8rem);
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 1rem);
    }}
    .direct-comparison__matches-wrapper {{
      margin-bottom: clamp(0.75rem, 2.6vw, 1.15rem);
    }}
    .direct-comparison__heading {{
      text-transform: none;
    }}
    .direct-comparison__cell {{
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.85rem);
    }}
    .direct-comparison__cell--meta {{
      white-space: nowrap;
    }}
    .direct-comparison__cell--result {{
      font-weight: 600;
      text-align: right;
    }}
    .direct-comparison__result--win {{
      color: {HIGHLIGHT_COLORS['usc']['row_text']};
    }}
    .direct-comparison__result--loss {{
      color: #b91c1c;
    }}
    .direct-comparison__result--neutral {{
      color: #0f172a;
    }}
    .direct-comparison__note {{
      margin: clamp(0.25rem, 1.2vw, 0.55rem) 0 0;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.8rem);
      color: #475569;
    }}
    .direct-comparison__fallback {{
      margin: 0;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.9rem);
      color: #475569;
      text-align: center;
      font-weight: 500;
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
      font-family: "Fira Mono", "SFMono-Regular", Menlo, Consolas, monospace;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 1.1rem);
      color: #0f766e;
      font-weight: 600;
    }}
    .match-meta {{
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.85rem);
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
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.92rem);
    }}
    .match-stats summary::-webkit-details-marker {{
      display: none;
    }}
    .match-stats summary::after {{
      content: "▾";
      margin-left: auto;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.9rem);
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
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.8rem);
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
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.9rem);
      font-weight: 600;
      color: #0f172a;
    }}
    .match-stats-table tbody td {{
      text-align: center;
      padding: 0.65rem 0.7rem;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.9rem);
      font-weight: 500;
      color: #1f2937;
    }}
    .match-stats-table tbody td.match-stats-value {{
      text-align: center;
    }}
    .match-stats-table tbody tr + tr th,
    .match-stats-table tbody tr + tr td {{
      border-top: 1px solid #e2e8f0;
    }}
    .match-stats-table tbody tr[data-team-role="usc"] {{
      background: var(--usc-highlight-row-bg);
      color: var(--usc-highlight-row-text);
    }}
    .match-stats-table tbody tr[data-team-role="usc"] th,
    .match-stats-table tbody tr[data-team-role="usc"] td {{
      color: inherit;
    }}
    .match-stats-table tbody tr[data-team-role="opponent"] {{
      background: var(--opponent-highlight-row-bg);
      color: var(--opponent-highlight-row-text);
    }}
    .match-stats-table tbody tr[data-team-role="opponent"] th,
    .match-stats-table tbody tr[data-team-role="opponent"] td {{
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
      border-color: var(--usc-highlight-card-border);
      box-shadow: 0 14px 30px var(--usc-highlight-card-shadow);
    }}
    .match-stats-card[data-team-role="opponent"] {{
      border-color: var(--opponent-highlight-card-border);
      box-shadow: 0 14px 30px var(--opponent-highlight-card-shadow);
    }}
    .match-stats-card h4 {{
      margin: 0 0 0.5rem 0;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.95rem);
      font-weight: 600;
      color: #0f172a;
    }}
    .match-stats-card pre {{
      margin: 0;
      font-family: \"Fira Mono\", \"SFMono-Regular\", Menlo, Consolas, monospace;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.75rem);
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
      font-size: calc(var(--font-scale) * var(--font-context-scale) * clamp(1rem, 2.6vw, 1.2rem));
    }}
    .accordion summary::-webkit-details-marker {{
      display: none;
    }}
    .accordion summary::after {{
      content: \"▾\";
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 1rem);
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
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.85rem);
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
      font-size: calc(var(--font-scale) * var(--font-context-scale) * clamp(1rem, 2.4vw, 1.15rem));
      background: var(--mvp-overview-summary-bg);
      border-bottom: 1px solid rgba(15, 23, 42, 0.08);
      color: #ffffff;
    }}
    .mvp-overview summary::-webkit-details-marker {{
      display: none;
    }}
    .mvp-overview summary::after {{
      content: "▾";
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 1rem);
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
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.85rem);
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
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.75rem);
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
      background: var(--usc-highlight-legend-dot);
    }}
    .mvp-legend-item[data-team="opponent"]::before {{
      background: var(--opponent-highlight-legend-dot);
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
      font-size: calc(var(--font-scale) * var(--font-context-scale) * clamp(0.95rem, 2.2vw, 1.1rem));
      gap: 0.6rem;
      background: rgba(15, 118, 110, 0.08);
    }}
    .mvp-category summary::-webkit-details-marker {{
      display: none;
    }}
    .mvp-category summary::after {{
      content: "▾";
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.95rem);
      transition: transform 0.2s ease;
      color: inherit;
    }}
    .mvp-category[open] summary::after {{
      transform: rotate(180deg);
    }}
    .mvp-category-title {{
      flex: 1;
      color: #0f766e;
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
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.7rem);
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
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.95rem);
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
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.95rem);
    }}
    .mvp-entry-meta {{
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.78rem);
      color: #475569;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }}
    .mvp-entry-score {{
      font-weight: 700;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.95rem);
      color: #0f4c75;
      justify-self: end;
    }}
    .mvp-entry[data-team="opponent"] {{
      background: var(--opponent-highlight-mvp-bg);
      box-shadow: inset 0 0 0 1px var(--opponent-highlight-mvp-border);
    }}
    .mvp-entry[data-team="opponent"] .mvp-entry-score {{
      color: var(--opponent-highlight-mvp-score);
    }}
    .mvp-entry[data-team="usc"] {{
      background: var(--usc-highlight-mvp-bg);
      box-shadow: inset 0 0 0 1px var(--usc-highlight-mvp-border);
    }}
    .mvp-entry[data-team="usc"] .mvp-entry-score {{
      color: var(--usc-highlight-mvp-score);
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
    @media (max-width: 30rem) {{
      .match-stats summary {{
        font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.82rem);
      }}
      .match-stats-table {{
        min-width: min(16rem, 100%);
      }}
      .match-stats-table thead th {{
        font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.62rem);
        padding: 0.3rem 0.35rem;
      }}
      .match-stats-table tbody th,
      .match-stats-table tbody td {{
        font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.7rem);
        padding: 0.35rem 0.35rem;
      }}
    }}
    .mvp-empty {{
      margin: 0;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.9rem);
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
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.95rem);
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
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.85rem);
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
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.95rem);
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
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 1rem);
    }}
    .roster-details {{
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.82rem);
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
      font-size: calc(var(--font-scale) * var(--font-context-scale) * clamp(1.05rem, 3vw, 1.3rem));
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
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.8rem);
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
      font-size: calc(var(--font-scale) * var(--font-context-scale) * clamp(1.05rem, 3vw, 1.3rem));
      color: #0f172a;
    }}
    .season-results-list {{
      margin: 0;
      padding-left: 1rem;
      display: grid;
      gap: 0.35rem;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.9rem);
      color: #1f2933;
    }}
    .season-results-fallback {{
      margin: 0;
      font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.9rem);
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
      font-size: calc(var(--font-scale) * var(--font-context-scale) * clamp(0.95rem, 2.5vw, 1.1rem));
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
        font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.85rem);
      }}
      h1 {{
        font-size: calc(var(--font-scale) * var(--font-context-scale) * 1.6rem);
      }}
      h2 {{
        font-size: calc(var(--font-scale) * var(--font-context-scale) * 1.1rem);
      }}
      .match-list li {{
        padding: 0.85rem 1rem;
      }}
      .direct-comparison__metrics {{
        grid-template-columns: 1fr;
        gap: clamp(0.5rem, 3vw, 0.7rem);
      }}
      .direct-comparison__metric {{
        padding: clamp(0.55rem, 3vw, 0.85rem);
      }}
      .direct-comparison__metric-value {{
        font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.95rem);
      }}
      .direct-comparison__metric-team {{
        font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.78rem);
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
        font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.8rem);
      }}
      .match-stats summary {{
        font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.9rem);
      }}
      .match-stats-table {{
        min-width: min(18rem, 100%);
      }}
      .match-stats-table thead th {{
        font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.68rem);
        padding: 0.35rem 0.45rem;
      }}
      .match-stats-table tbody th,
      .match-stats-table tbody td {{
        font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.78rem);
        padding: 0.4rem 0.45rem;
      }}
      .accordion summary {{
        font-size: calc(var(--font-scale) * var(--font-context-scale) * 1.05rem);
      }}
      .mvp-overview summary {{
        font-size: calc(var(--font-scale) * var(--font-context-scale) * 1.05rem);
      }}
      .roster-item {{
        grid-template-columns: minmax(3rem, auto) 1fr;
      }}
      .roster-number {{
        font-size: calc(var(--font-scale) * var(--font-context-scale) * 0.8rem);
        padding: 0.3rem 0.5rem;
      }}
      .team-photo {{
        margin-bottom: 0.9rem;
      }}
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --accordion-opponent-bg: {HIGHLIGHT_COLORS['opponent']['dark_accordion_bg']};
        --accordion-opponent-shadow: {HIGHLIGHT_COLORS['opponent']['dark_accordion_shadow']};
        --accordion-usc-bg: {HIGHLIGHT_COLORS['usc']['dark_accordion_bg']};
        --accordion-usc-shadow: {HIGHLIGHT_COLORS['usc']['dark_accordion_shadow']};
        --usc-highlight-row-bg: {HIGHLIGHT_COLORS['usc']['dark_row_bg']};
        --usc-highlight-row-text: {HIGHLIGHT_COLORS['usc']['dark_row_text']};
        --opponent-highlight-row-bg: {HIGHLIGHT_COLORS['opponent']['dark_row_bg']};
        --opponent-highlight-row-text: {HIGHLIGHT_COLORS['opponent']['dark_row_text']};
        --mvp-overview-summary-bg: {THEME_COLORS['dark_mvp_overview_summary_bg']};
        --theme-color: {THEME_COLORS['dark_mvp_overview_summary_bg']};
      }}
      body {{
        background: #0e1b1f;
        color: #e6f1f3;
      }}
      .broadcast-box {{
        background: radial-gradient(circle at top left, rgba(15, 118, 110, 0.55), rgba(8, 47, 73, 0.9));
        border-color: rgba(125, 211, 252, 0.22);
        box-shadow: 0 26px 52px rgba(8, 47, 73, 0.55);
      }}
      .broadcast-box__summary {{
        color: #e0f2fe;
      }}
      .broadcast-box__summary-title {{
        color: #e0f2fe;
      }}
      .broadcast-box__summary-indicator {{
        border-color: rgba(125, 211, 252, 0.55);
        color: #bae6fd;
        background: rgba(8, 145, 178, 0.18);
      }}
      .broadcast-box__details[open] .broadcast-box__summary-indicator {{
        border-color: rgba(56, 189, 248, 0.75);
        background: rgba(15, 118, 110, 0.35);
        color: #f0fdfa;
      }}
      .broadcast-box__content {{
        background: linear-gradient(145deg, rgba(12, 74, 110, 0.55), rgba(8, 47, 73, 0.75));
        border-radius: 0.85rem;
        padding: clamp(0.35rem, 1.4vw, 0.75rem);
        box-shadow: inset 0 0 0 1px rgba(14, 165, 233, 0.15);
      }}
      .broadcast-table-wrapper {{
        background: rgba(8, 47, 73, 0.65);
        border-color: rgba(148, 163, 184, 0.32);
      }}
      .broadcast-table thead th {{
        background: linear-gradient(135deg, rgba(13, 148, 136, 0.35), rgba(59, 130, 246, 0.18));
        color: #99f6e4;
        border-bottom-color: rgba(20, 184, 166, 0.35);
      }}
      .broadcast-table tbody th,
      .broadcast-table tbody td {{
        border-top-color: rgba(51, 65, 85, 0.6);
      }}
      .broadcast-table tbody tr:nth-child(even) {{
        background: rgba(15, 118, 110, 0.15);
      }}
      .broadcast-cell--time {{
        color: #ccfbf1;
      }}
      .broadcast-cell--countdown {{
        color: #5eead4;
        text-shadow: 0 0 8px rgba(94, 234, 212, 0.45);
      }}
      .broadcast-cell--note {{
        color: #e0f2fe;
      }}
      .broadcast-cell--duration {{
        color: #bfdbfe;
      }}
      .broadcast-cell--duration,
      .broadcast-empty {{
        color: #bfdbfe;
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
      .direct-comparison__metric {{
        background: rgba(15, 118, 110, 0.22);
        box-shadow: 0 16px 32px rgba(0, 0, 0, 0.4);
      }}
      .direct-comparison__metric-label {{
        color: #5eead4;
      }}
      .direct-comparison__metric-value {{
        color: #bbf7d0;
      }}
      .direct-comparison__metric-team {{
        color: #f0fdfa;
      }}
      .direct-comparison__metric-team--opponent {{
        color: #bae6fd;
      }}
      .direct-comparison__last-meeting {{
        background: rgba(15, 118, 110, 0.18);
        box-shadow: 0 16px 32px rgba(0, 0, 0, 0.35);
      }}
      .direct-comparison__last-meta {{
        color: #bfdbfe;
      }}
      .direct-comparison__last-result {{
        color: #e0f2fe;
      }}
      .direct-comparison__result--loss {{
        color: #fca5a5;
      }}
      .direct-comparison__result--neutral {{
        color: #f1f5f9;
      }}
      .direct-comparison__note {{
        color: #cbd5f5;
      }}
      .direct-comparison__fallback {{
        color: #94a3b8;
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
        background: var(--usc-highlight-row-bg);
        color: var(--usc-highlight-row-text);
      }}
      .match-stats-table tbody tr[data-team-role="opponent"] {{
        background: var(--opponent-highlight-row-bg);
        color: var(--opponent-highlight-row-text);
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
        background: var(--mvp-overview-summary-bg);
        border-bottom: 1px solid rgba(148, 163, 184, 0.35);
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
      .pwa-install-banner {{
        box-shadow: 0 22px 44px rgba(8, 47, 73, 0.55);
      }}
      .pwa-install-button {{
        color: {THEME_COLORS['mvp_overview_summary_bg']};
      }}
      .pwa-install-dismiss {{
        color: #e2f3f7;
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
      .countdown-meta__kickoff {{
        color: #ccfbf1;
      }}
      .countdown-meta__location {{
        color: #bae6fd;
      }}
      .countdown-meta__competition {{
        color: #7dd3fc;
      }}
      .countdown-banner {{
        background: linear-gradient(135deg, rgba(20, 184, 166, 0.85), rgba(14, 165, 233, 0.65));
        color: #ecfeff;
        box-shadow: 0 20px 44px rgba(14, 165, 233, 0.35);
      }}
      .countdown-banner--live {{
        background: linear-gradient(135deg, rgba(248, 113, 113, 0.92), rgba(249, 115, 22, 0.88));
        box-shadow: 0 22px 48px rgba(185, 28, 28, 0.45);
      }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>Nächster USC-Heimgegner:<br><span data-next-opponent>{escape(heading)}</span></h1>
{hero_layout_html}
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
{direct_comparison_html}
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
  <script>
    (() => {{
      const themeColor = "{THEME_COLORS['mvp_overview_summary_bg']}";
      const themeMeta = document.querySelector('meta[name="theme-color"]');
      if (themeMeta) {{
        themeMeta.setAttribute("content", themeColor);
      }}

      const createTimeZoneOffsetGetter = (timeZone) => {{
        try {{
          const formatter = new Intl.DateTimeFormat('en-US', {{
            timeZone,
            hour12: false,
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
          }});
          return (date) => {{
            const parts = formatter.formatToParts(date);
            let year;
            let month;
            let day;
            let hour;
            let minute;
            let second;
            for (const part of parts) {{
              if (part.type === 'year') {{
                year = Number(part.value);
              }} else if (part.type === 'month') {{
                month = Number(part.value);
              }} else if (part.type === 'day') {{
                day = Number(part.value);
              }} else if (part.type === 'hour') {{
                hour = Number(part.value);
              }} else if (part.type === 'minute') {{
                minute = Number(part.value);
              }} else if (part.type === 'second') {{
                second = Number(part.value);
              }}
            }}

            if (
              year === undefined ||
              month === undefined ||
              day === undefined ||
              hour === undefined ||
              minute === undefined ||
              second === undefined
            ) {{
              return Number.NaN;
            }}

            const utcMillis = Date.UTC(
              year,
              month - 1,
              day,
              hour,
              minute,
              second,
            );
            return (date.getTime() - utcMillis) / 60000;
          }};
        }} catch (error) {{
          return null;
        }}
      }};

      const banner = document.querySelector('[data-countdown-banner]');
      if (banner) {{
        const iso = banner.getAttribute('data-kickoff');
        const timeZone = banner.getAttribute('data-timezone') || '{BERLIN_TIMEZONE_NAME}';
        if (iso) {{
          const targetMs = Date.parse(iso);
          if (!Number.isNaN(targetMs)) {{
            const getOffset = createTimeZoneOffsetGetter(timeZone);
            const targetDate = new Date(targetMs);
            const targetOffset = getOffset ? getOffset(targetDate) : Number.NaN;
            const heading = banner.querySelector('[data-countdown-heading]');
            const display = banner.querySelector('[data-countdown-display]');
            const pad = (value) => String(value).padStart(2, '0');
            const plural = (value, singular, pluralForm) =>
              value + ' ' + (value === 1 ? singular : pluralForm);
            const update = () => {{
              const now = new Date();
              let diff = targetMs - now.getTime();

              if (
                getOffset &&
                Number.isFinite(targetOffset)
              ) {{
                const nowOffset = getOffset(now);
                if (Number.isFinite(nowOffset)) {{
                  diff -= (targetOffset - nowOffset) * 60000;
                }}
              }}

              const isLive = diff <= 0;
              const totalSeconds = Math.floor(Math.abs(diff) / 1000);
              const days = Math.floor(totalSeconds / 86400);
              const hours = Math.floor((totalSeconds % 86400) / 3600);
              const minutes = Math.floor((totalSeconds % 3600) / 60);
              const seconds = totalSeconds % 60;
              const parts = [];
              if (days > 0) {{
                parts.push(plural(days, 'Tag', 'Tage'));
              }}
              let timeLabel = pad(hours) + ':' + pad(minutes) + ':' + pad(seconds);
              if (isLive) {{
                timeLabel = '+' + timeLabel;
                banner.classList.add('countdown-banner--live');
                if (heading) {{
                  heading.textContent = 'Live';
                }}
              }} else {{
                banner.classList.remove('countdown-banner--live');
                if (heading) {{
                  heading.textContent = 'Countdown';
                }}
              }}
              parts.push(timeLabel);
              if (display) {{
                display.textContent = parts.join(' · ');
              }}
            }};

            update();
            window.setInterval(update, 1000);
          }}
        }}
      }}

      const stopwatch = document.querySelector('[data-stopwatch]');
      if (stopwatch) {{
        const display = stopwatch.querySelector('[data-stopwatch-display]');
        const startButton = stopwatch.querySelector('[data-stopwatch-start]');
        const stopButton = stopwatch.querySelector('[data-stopwatch-stop]');
        const resetButton = stopwatch.querySelector('[data-stopwatch-reset]');

        let startTimestamp = 0;
        let accumulatedMs = 0;
        let intervalId;

        const formatTime = (totalMs) => {{
          const totalSeconds = Math.floor(totalMs / 1000);
          const minutes = Math.floor(totalSeconds / 60);
          const seconds = totalSeconds % 60;
          return (
            String(minutes).padStart(2, '0') + ':' + String(seconds).padStart(2, '0')
          );
        }};

        const stopInterval = () => {{
          if (typeof intervalId === 'number') {{
            window.clearInterval(intervalId);
          }}
          intervalId = undefined;
        }};

        const render = () => {{
          const runningMs = startTimestamp ? Date.now() - startTimestamp : 0;
          const totalMs = accumulatedMs + Math.max(runningMs, 0);
          if (display) {{
            display.textContent = formatTime(totalMs);
          }}
        }};

        const setRunning = (running) => {{
          stopwatch.classList.toggle('stopwatch--running', running);
        }};

        const start = () => {{
          if (startTimestamp) {{
            return;
          }}
          startTimestamp = Date.now();
          stopInterval();
          intervalId = window.setInterval(render, 200);
          setRunning(true);
          render();
        }};

        const stop = () => {{
          if (!startTimestamp) {{
            return;
          }}
          accumulatedMs += Date.now() - startTimestamp;
          startTimestamp = 0;
          stopInterval();
          setRunning(false);
          render();
        }};

        const reset = () => {{
          accumulatedMs = 0;
          startTimestamp = 0;
          stopInterval();
          setRunning(false);
          render();
        }};

        startButton?.addEventListener('click', start);
        stopButton?.addEventListener('click', stop);
        resetButton?.addEventListener('click', reset);

        stopwatch.addEventListener('toggle', () => {{
          if (!stopwatch.open) {{
            stop();
          }}
        }});

        document.addEventListener('visibilitychange', () => {{
          if (document.visibilityState !== 'visible' && startTimestamp) {{
            accumulatedMs += Date.now() - startTimestamp;
            startTimestamp = Date.now();
          }}
          render();
        }});

        render();
      }}

    }})();
  </script>
</body>
</html>
"""

    return html


__all__ = [
    "BERLIN_TZ",
    "DEFAULT_SCHEDULE_URL",
    "DVV_POKAL_SCHEDULE_URL",
    "NEWS_LOOKBACK_DAYS",
    "NewsItem",
    "Match",
    "MatchResult",
    "RosterMember",
    "MatchStatsTotals",
    "TransferItem",
    "DirectComparisonData",
    "DirectComparisonMatch",
    "DirectComparisonSummary",
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
    "prepare_direct_comparison",
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
