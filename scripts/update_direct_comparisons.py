#!/usr/bin/env python3
"""Generate JSON dataset with USC Münster head-to-head records."""

from __future__ import annotations

import argparse
import csv
import json
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, Iterator, List, MutableMapping, Sequence, Tuple

import requests

USER_AGENT = {"User-Agent": "Mozilla/5.0 (compatible; usc-streaminginfos-bot/2.0)"}
DEFAULT_OUTPUT_PATH = Path("docs/data/direct_comparisons.json")
USC_KEYWORD = "usc"


@dataclass(frozen=True)
class SeasonSource:
    season: str
    urls: Sequence[str]


SEASON_SOURCES: Sequence[SeasonSource] = (
    SeasonSource(
        season="2025/26",
        urls=(
            "https://www.volleyball-bundesliga.de/servlet/league/PlayingScheduleCsvExport?matchSeriesId=776311171",
        ),
    ),
    SeasonSource(
        season="2024/25",
        urls=(
            "https://www.volleyball-bundesliga.de/servlet/league/PlayingScheduleCsvExport?matchSeriesId=770580199",
        ),
    ),
    SeasonSource(
        season="2023/24",
        urls=(
            "https://www.volleyball-bundesliga.de/servlet/league/PlayingScheduleCsvExport?matchSeriesId=766160508",
            "https://www.volleyball-bundesliga.de/servlet/league/PlayingScheduleCsvExport?matchSeriesId=766160398",
        ),
    ),
    SeasonSource(
        season="2022/23",
        urls=(
            "https://www.volleyball-bundesliga.de/servlet/league/PlayingScheduleCsvExport?matchSeriesId=758959411",
        ),
    ),
)

Row = MutableMapping[str, str | None]


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    stripped = "".join(char for char in normalized if not unicodedata.combining(char))
    return stripped.casefold()


def is_usc_team(name: str | None) -> bool:
    if not name:
        return False
    return USC_KEYWORD in _normalize(name)


def fetch_csv_rows(url: str) -> Iterator[Row]:
    response = requests.get(url, headers=USER_AGENT, timeout=30)
    response.raise_for_status()
    decoded = response.text
    reader = csv.DictReader(decoded.splitlines(), delimiter=";")
    for row in reader:
        yield row


def parse_pair(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned or ":" not in cleaned:
        return None
    left, right = cleaned.split(":", 1)
    try:
        return int(left.strip()), int(right.strip())
    except ValueError:
        return None


def extract_sets(row: Row) -> tuple[int, int] | None:
    direct = parse_pair(row.get("Satzpunkte"))
    if direct:
        return direct
    ergebnis = row.get("Ergebnis")
    if ergebnis and "/" in ergebnis:
        sets_part = ergebnis.split("/", 1)[0]
        direct = parse_pair(sets_part)
        if direct:
            return direct
    combined = row.get("Austragungsort/Ergebnis")
    if combined and "/" in combined:
        sets_part = combined.split("/", 1)[0]
        direct = parse_pair(sets_part)
        if direct:
            return direct
    return None


def extract_points(row: Row) -> tuple[int, int] | None:
    points = parse_pair(row.get("Ballpunkte"))
    if points:
        return points
    ergebnis = row.get("Ergebnis")
    if ergebnis and "/" in ergebnis:
        _, points_part = ergebnis.split("/", 1)
        points = parse_pair(points_part)
        if points:
            return points
    combined = row.get("Austragungsort/Ergebnis")
    if combined and "/" in combined:
        _, points_part = combined.split("/", 1)
        points = parse_pair(points_part)
        if points:
            return points
    return None


def extract_set_ballpoints(row: Row) -> Tuple[Tuple[int, int], ...]:
    scores: List[Tuple[int, int]] = []
    for index in range(1, 6):
        home_key = f"Satz {index} - Ballpunkte 1"
        away_key = f"Satz {index} - Ballpunkte 2"
        home_raw = row.get(home_key)
        away_raw = row.get(away_key)
        home_text = (home_raw or "").strip()
        away_text = (away_raw or "").strip()
        if not home_text and not away_text:
            break
        try:
            home_points = int(home_text)
            away_points = int(away_text)
        except (TypeError, ValueError):
            break
        scores.append((home_points, away_points))
    return tuple(scores)


def parse_date(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%d.%m.%Y").date().isoformat()
    except ValueError:
        return None


def clean_dict(data: MutableMapping[str, object]) -> Dict[str, object]:
    return {key: value for key, value in data.items() if value is not None}


def build_dataset(sources: Sequence[SeasonSource]) -> Dict[str, object]:
    seasons_payload: List[Dict[str, object]] = []
    for source in sources:
        opponents: Dict[str, Dict[str, object]] = {}
        seen_match_ids: set[str] = set()
        for url in source.urls:
            for row in fetch_csv_rows(url):
                team_home = row.get("Mannschaft 1") or ""
                team_away = row.get("Mannschaft 2") or ""
                if not (is_usc_team(team_home) or is_usc_team(team_away)):
                    continue
                sets_pair = extract_sets(row)
                if sets_pair is None:
                    continue
                match_identifier = (row.get("#") or "").strip()
                if match_identifier:
                    if match_identifier in seen_match_ids:
                        continue
                    seen_match_ids.add(match_identifier)

                usc_is_home = is_usc_team(team_home)
                opponent_name = team_away if usc_is_home else team_home
                usc_sets, opponent_sets = sets_pair if usc_is_home else (sets_pair[1], sets_pair[0])
                points_pair = extract_points(row)
                if points_pair:
                    usc_points, opponent_points = (points_pair if usc_is_home else (points_pair[1], points_pair[0]))
                else:
                    usc_points = opponent_points = None

                round_label = row.get("ST")
                competition = row.get("Spielrunde")
                date_iso = parse_date(row.get("Datum"))
                location = row.get("Austragungsort") or None
                points_str = None
                if points_pair:
                    points_str = f"{points_pair[0]}:{points_pair[1]}"

                set_scores_pairs = extract_set_ballpoints(row)
                if usc_is_home:
                    oriented_set_scores = [
                        f"{home}:{away}" for home, away in set_scores_pairs
                    ]
                else:
                    oriented_set_scores = [
                        f"{away}:{home}" for home, away in set_scores_pairs
                    ]
                set_scores_value: List[str] | None
                if oriented_set_scores:
                    set_scores_value = oriented_set_scores
                else:
                    set_scores_value = None

                match_record = clean_dict(
                    {
                        "match_id": match_identifier or None,
                        "date": date_iso,
                        "home_team": team_home or None,
                        "away_team": team_away or None,
                        "round": round_label or None,
                        "competition": competition or None,
                        "location": location,
                        "set_scores": set_scores_value,
                        "result": clean_dict(
                            {
                                "sets": row.get("Satzpunkte") or (row.get("Ergebnis") or "").split("/", 1)[0].strip() or None,
                                "points": points_str,
                            }
                        ),
                        "usc_sets": usc_sets,
                        "opponent_sets": opponent_sets,
                        "usc_points": usc_points,
                        "opponent_points": opponent_points,
                        "usc_won": usc_sets > opponent_sets,
                    }
                )

                bucket = opponents.setdefault(
                    opponent_name,
                    {
                        "team": opponent_name,
                        "matches": [],
                        "summary": {
                            "matches_played": 0,
                            "usc_wins": 0,
                            "usc_losses": 0,
                            "usc_sets_for": 0,
                            "usc_sets_against": 0,
                            "usc_points_for": 0,
                            "usc_points_against": 0,
                        },
                    },
                )
                bucket["matches"].append(match_record)
                summary = bucket["summary"]
                summary["matches_played"] += 1
                if usc_sets > opponent_sets:
                    summary["usc_wins"] += 1
                else:
                    summary["usc_losses"] += 1
                summary["usc_sets_for"] += usc_sets
                summary["usc_sets_against"] += opponent_sets
                if usc_points is not None and opponent_points is not None:
                    summary["usc_points_for"] += usc_points
                    summary["usc_points_against"] += opponent_points
        # sort matches chronologically per opponent
        for payload in opponents.values():
            payload["matches"].sort(key=lambda item: (item.get("date") or "", item.get("match_id") or ""))
        opponents_list = [
            {
                "team": team_name,
                "summary": data["summary"],
                "matches": data["matches"],
            }
            for team_name, data in sorted(opponents.items())
        ]
        seasons_payload.append(
            {
                "season": source.season,
                "opponents": opponents_list,
            }
        )
    generated_at = datetime.now(UTC).replace(microsecond=0)
    return {
        "team": "USC Münster",
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "seasons": seasons_payload,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Erzeuge eine JSON-Datei mit direkten Vergleichen aller USC-Gegner.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Pfad für die erzeugte JSON-Datei (Standard: docs/data/direct_comparisons.json).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    dataset = build_dataset(SEASON_SOURCES)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
