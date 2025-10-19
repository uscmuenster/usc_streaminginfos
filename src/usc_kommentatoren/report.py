from __future__ import annotations

import csv
import time
from dataclasses import dataclass
import re
from datetime import datetime, timedelta
from pathlib import Path
from html import escape
from io import StringIO
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo
from urllib.parse import urljoin
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

DEFAULT_SCHEDULE_URL = "https://www.volleyball-bundesliga.de/servlet/league/PlayingScheduleCsvExport?matchSeriesId=776311171"
TABLE_URL = "https://www.volleyball-bundesliga.de/cms/home/1_bundesliga_frauen/statistik/hauptrunde/tabelle_hauptrunde.xhtml"
VBL_NEWS_URL = "https://www.volleyball-bundesliga.de/cms/home/1_bundesliga_frauen/news/news.xhtml"
VBL_PRESS_URL = "https://www.volleyball-bundesliga.de/cms/home/1_bundesliga_frauen/news/pressespiegel.xhtml"
BERLIN_TZ = ZoneInfo("Europe/Berlin")
USC_CANONICAL_NAME = "USC Münster"
USC_HOMEPAGE = "https://www.usc-muenster.de/"

REQUEST_HEADERS = {"User-Agent": "usc-kommentatoren/1.0 (+https://github.com/)"}
HTML_ACCEPT_HEADER = {"Accept": "text/html,application/xhtml+xml"}
RSS_ACCEPT_HEADER = {"Accept": "application/rss+xml,text/xml"}
NEWS_LOOKBACK_DAYS = 14

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
class Match:
    kickoff: datetime
    home_team: str
    away_team: str
    host: str
    location: str
    result: Optional[MatchResult]

    @property
    def is_finished(self) -> bool:
        return self.result is not None


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
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> requests.Response:
    last_error: Optional[Exception] = None
    merged_headers = dict(REQUEST_HEADERS)
    if headers:
        merged_headers.update(headers)
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=30, headers=merged_headers)
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
) -> str:
    response = _http_get(
        url,
        headers={**HTML_ACCEPT_HEADER, **(headers or {})},
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

        matches.append(
            Match(
                kickoff=kickoff,
                home_team=home_team,
                away_team=away_team,
                host=host,
                location=location,
                result=result,
            )
        )
    return matches


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


def get_team_homepage(team_name: str) -> Optional[str]:
    return TEAM_HOMEPAGES.get(normalize_name(team_name))


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


def format_match_line(match: Match) -> str:
    date_label = match.kickoff.strftime("%d.%m.%Y")
    weekday = GERMAN_WEEKDAYS.get(match.kickoff.weekday(), match.kickoff.strftime("%a"))
    kickoff_label = f"{date_label} ({weekday})"
    home = pretty_name(match.home_team)
    away = pretty_name(match.away_team)
    result = match.result.summary if match.result else "-"
    teams = f"{home} vs. {away}"
    return (
        "<li>"
        "<div class=\"match-line\">"
        f"<div class=\"match-header\"><strong>{escape(kickoff_label)}</strong> – {escape(teams)}</div>"
        f"<div class=\"match-result\">Ergebnis: {escape(result)}</div>"
        "</div>"
        "</li>"
    )


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


def build_html_report(
    *,
    next_home: Match,
    usc_recent: List[Match],
    opponent_recent: List[Match],
    usc_news: Sequence[NewsItem],
    opponent_news: Sequence[NewsItem],
    public_url: Optional[str] = None,
) -> str:
    heading = pretty_name(next_home.away_team)
    kickoff = next_home.kickoff.strftime("%d.%m.%Y %H:%M")
    location = pretty_name(next_home.location)
    usc_url = get_team_homepage(USC_CANONICAL_NAME) or USC_HOMEPAGE
    opponent_url = get_team_homepage(next_home.away_team)

    if usc_recent:
        usc_items = "\n      ".join(
            format_match_line(match) for match in usc_recent
        )
    else:
        usc_items = "<li>Keine Daten verfügbar.</li>"

    if opponent_recent:
        opponent_items = "\n      ".join(
            format_match_line(match) for match in opponent_recent
        )
    else:
        opponent_items = "<li>Keine Daten verfügbar.</li>"

    usc_news_items = format_news_list(usc_news)
    opponent_news_items = format_news_list(opponent_news)

    usc_link_block = ""
    if usc_url:
        safe_usc_url = escape(usc_url)
        usc_link_block = (
            f"      <p><a class=\"meta-link\" href=\"{safe_usc_url}\">Homepage USC Münster</a></p>\n"
        )

    opponent_link_block = ""
    if opponent_url:
        safe_opponent_url = escape(opponent_url)
        opponent_link_block = (
            f"      <p><a class=\"meta-link\" href=\"{safe_opponent_url}\">Homepage {escape(heading)}</a></p>\n"
        )

    public_url_block = ""
    if public_url:
        safe_url = escape(public_url)
        public_url_block = (
            f"      <p><a class=\"meta-link\" href=\"{safe_url}\">Öffentliche Adresse</a></p>\n"
        )

    html = f"""<!DOCTYPE html>
<html lang=\"de\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Nächster USC-Heimgegner</title>
  <style>
    :root {{ color-scheme: light dark; }}
    body {{
      margin: 0;
      font-family: "Inter", "Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
      line-height: 1.6;
      background: #f5f7f9;
      color: #1f2933;
    }}
    main {{
      max-width: 60rem;
      margin: 0 auto;
      padding: clamp(1.25rem, 4vw, 3rem);
    }}
    h1 {{
      color: #004c54;
      font-size: clamp(1.8rem, 5vw, 2.6rem);
      margin-bottom: 1.25rem;
    }}
    h2 {{
      font-size: clamp(1.3rem, 4vw, 1.75rem);
      margin-bottom: 1rem;
    }}
    section {{
      margin-top: clamp(1.75rem, 4vw, 2.75rem);
    }}
    .meta {{
      display: grid;
      gap: 0.35rem;
      margin: 0 0 1.5rem 0;
      padding: 0;
    }}
    .meta p {{
      margin: 0;
    }}
    .match-list {{
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 1rem;
    }}
    .match-list li {{
      background: #ffffff;
      border-radius: 0.85rem;
      padding: 1rem clamp(1rem, 3vw, 1.5rem);
      box-shadow: 0 10px 30px rgba(0, 76, 84, 0.08);
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
      font-size: 0.95rem;
      color: #0f766e;
    }}
    .news-group {{
      margin-top: 1.75rem;
      display: grid;
      gap: 1rem;
    }}
    .accordion {{
      border-radius: 0.85rem;
      overflow: hidden;
      background: #e0f2f1;
      box-shadow: 0 18px 40px rgba(0, 0, 0, 0.08);
      border: none;
    }}
    .accordion summary {{
      cursor: pointer;
      padding: 1rem 1.35rem;
      font-weight: 600;
      display: flex;
      align-items: center;
      justify-content: space-between;
      list-style: none;
      font-size: clamp(1.05rem, 3vw, 1.25rem);
    }}
    .accordion summary::-webkit-details-marker {{
      display: none;
    }}
    .accordion summary::after {{
      content: "▾";
      font-size: 1rem;
      transition: transform 0.2s ease;
    }}
    .accordion[open] summary::after {{
      transform: rotate(180deg);
    }}
    .accordion-content {{
      padding: 0 1.35rem 1.35rem;
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
      font-size: 0.85rem;
      color: #64748b;
      margin-top: 0.2rem;
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
    @media (max-width: 40rem) {{
      .match-list li {{
        padding: 0.85rem 1rem;
      }}
      .match-result {{
        font-size: 0.95rem;
      }}
    }}
    @media (prefers-color-scheme: dark) {{
      body {{
        background: #0e1b1f;
        color: #e6f1f3;
      }}
      .match-list li {{
        background: #132a30;
        box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
      }}
      .accordion {{
        background: #0f2529;
        box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
      }}
      .match-result {{
        color: #5eead4;
      }}
      a {{
        color: #5eead4;
      }}
      h1 {{
        color: #5eead4;
      }}
      .news-meta {{
        color: #94a3b8;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>Nächster USC-Heimgegner:<br>{escape(heading)}</h1>
    <div class=\"meta\">
      <p><strong>Spieltermin:</strong> {escape(kickoff)} Uhr</p>
      <p><strong>Austragungsort:</strong> {escape(location)}</p>
      <p><a class=\"meta-link\" href=\"{TABLE_URL}\">Tabelle der Volleyball Bundesliga</a></p>
{usc_link_block}{opponent_link_block}{public_url_block}    </div>
    <section>
      <h2>Letzte Spiele von {escape(heading)}</h2>
      <ul class=\"match-list\">
        {opponent_items}
      </ul>
    </section>
    <section>
      <h2>Letzte Spiele von {escape(USC_CANONICAL_NAME)}</h2>
      <ul class=\"match-list\">
        {usc_items}
      </ul>
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
  </main>
</body>
</html>
"""

    return html


__all__ = [
    "DEFAULT_SCHEDULE_URL",
    "NEWS_LOOKBACK_DAYS",
    "NewsItem",
    "Match",
    "MatchResult",
    "TEAM_HOMEPAGES",
    "TABLE_URL",
    "VBL_NEWS_URL",
    "VBL_PRESS_URL",
    "USC_HOMEPAGE",
    "collect_team_news",
    "build_html_report",
    "download_schedule",
    "fetch_team_news",
    "fetch_schedule",
    "find_last_matches_for_team",
    "find_next_usc_home_match",
    "get_team_homepage",
    "load_schedule_from_file",
    "parse_schedule",
]
