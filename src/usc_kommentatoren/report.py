from __future__ import annotations

import csv
import time
from dataclasses import dataclass
import re
from datetime import datetime
from pathlib import Path
from html import escape
from io import StringIO
from typing import Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

import requests

DEFAULT_SCHEDULE_URL = "https://www.volleyball-bundesliga.de/servlet/league/PlayingScheduleCsvExport?matchSeriesId=776311171"
TABLE_URL = "https://www.volleyball-bundesliga.de/cms/home/1_bundesliga_frauen/statistik/hauptrunde/tabelle_hauptrunde.xhtml"
BERLIN_TZ = ZoneInfo("Europe/Berlin")
USC_CANONICAL_NAME = "USC Münster"
USC_HOMEPAGE = "https://www.usc-muenster.de/"


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


def _download_schedule_text(
    url: str,
    *,
    retries: int = 5,
    delay_seconds: float = 2.0,
) -> str:
    last_error: Optional[Exception] = None
    for attempt in range(retries):
        try:
            response = requests.get(
                url,
                timeout=30,
                headers={"User-Agent": "usc-kommentatoren/1.0 (+https://github.com/)"},
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:  # pragma: no cover - network errors
            last_error = exc
            if attempt == retries - 1:
                raise
            backoff = delay_seconds * (2 ** attempt)
            time.sleep(backoff)
    else:  # pragma: no cover
        if last_error:
            raise last_error
        raise RuntimeError("Unbekannter Fehler beim Abrufen des Spielplans.")


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


def build_html_report(
    *,
    next_home: Match,
    usc_recent: List[Match],
    opponent_recent: List[Match],
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
    ul {{
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 1rem;
    }}
    li {{
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
      li {{
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
      li {{
        background: #132a30;
        box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
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
    }}
  </style>
</head>
<body>
  <main>
    <h1>Nächster USC-Heimgegner: {escape(heading)}</h1>
    <div class=\"meta\">
      <p><strong>Spieltermin:</strong> {escape(kickoff)} Uhr</p>
      <p><strong>Austragungsort:</strong> {escape(location)}</p>
      <p><a class=\"meta-link\" href=\"{TABLE_URL}\">Tabelle der Volleyball Bundesliga</a></p>
{usc_link_block}{opponent_link_block}{public_url_block}    </div>
    <section>
      <h2>Letzte Spiele von {escape(USC_CANONICAL_NAME)}</h2>
      <ul>
        {usc_items}
      </ul>
    </section>
    <section>
      <h2>Letzte Spiele von {escape(heading)}</h2>
      <ul>
        {opponent_items}
      </ul>
    </section>
  </main>
</body>
</html>
"""

    return html


__all__ = [
    "DEFAULT_SCHEDULE_URL",
    "Match",
    "MatchResult",
    "TEAM_HOMEPAGES",
    "TABLE_URL",
    "USC_HOMEPAGE",
    "build_html_report",
    "download_schedule",
    "fetch_schedule",
    "find_last_matches_for_team",
    "find_next_usc_home_match",
    "get_team_homepage",
    "load_schedule_from_file",
    "parse_schedule",
]
