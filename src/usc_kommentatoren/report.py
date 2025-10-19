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
    gap = "&nbsp;" * 5
    return (
        "<li>"
        f"<span class=\"match-header\"><strong>{escape(kickoff_label)}</strong> – {escape(teams)}</span>"
        f"{gap}<span class=\"match-result\">Ergebnis: {escape(result)}</span>"
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

    public_url_block = ""
    if public_url:
        safe_url = escape(public_url)
        public_url_block = (
            "  <p><strong>Öffentliche Adresse:</strong> "
            f"<a href=\"{safe_url}\">{safe_url}</a></p>\n"
        )

    html = f"""<!DOCTYPE html>
<html lang=\"de\">
<head>
  <meta charset=\"utf-8\">
  <title>Nächster USC-Heimgegner</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; line-height: 1.5; }}
    h1 {{ color: #004c54; }}
    section {{ margin-top: 2rem; }}
    ul {{ list-style: none; padding: 0; }}
    li {{ margin-bottom: 0.75rem; }}
    .match-header {{ display: inline; }}
    .match-result {{ white-space: nowrap; }}
  </style>
</head>
<body>
  <h1>Nächster USC-Heimgegner: {escape(heading)}</h1>
  <p><strong>Spieltermin:</strong> {escape(kickoff)} Uhr</p>
  <p><strong>Austragungsort:</strong> {escape(location)}</p>
  <p><strong>Tabelle:</strong> <a href=\"{TABLE_URL}\">{TABLE_URL}</a></p>
{public_url_block}
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
</body>
</html>
"""
    return html


__all__ = [
    "DEFAULT_SCHEDULE_URL",
    "Match",
    "MatchResult",
    "TABLE_URL",
    "build_html_report",
    "download_schedule",
    "fetch_schedule",
    "find_last_matches_for_team",
    "find_next_usc_home_match",
    "load_schedule_from_file",
    "parse_schedule",
]
