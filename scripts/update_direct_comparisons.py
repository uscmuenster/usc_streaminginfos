#!/usr/bin/env python3
"""Generate JSON dataset with head-to-head records for the configured home team."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, Iterator, List, MutableMapping, Optional, Sequence, Tuple

import requests

USER_AGENT = {"User-Agent": "Mozilla/5.0 (compatible; usc-streaminginfos-bot/2.0)"}
DEFAULT_OUTPUT_PATH = Path("docs/data/direct_comparisons.json")
_DEFAULT_HOME_TEAM = "USC Münster"


def _add_src_to_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


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


def is_home_team(name: str | None, home_team: str) -> bool:
    """Prüft, ob *name* dem konfigurierten Heimteam entspricht."""
    if not name:
        return False
    target = _normalize(home_team)
    candidate = _normalize(name)
    # Prüfe sowohl exakte Übereinstimmung als auch Teilstring-Match
    return target == candidate or target in candidate or candidate in target


def fetch_csv_rows(url: str) -> Iterator[Row]:
    response = requests.get(url, headers=USER_AGENT, timeout=30)
    response.raise_for_status()
    decoded = response.text
    reader = csv.DictReader(decoded.splitlines(), delimiter=";")
    for row in reader:
        yield {
            (key or "").strip().lstrip("\ufeff"): value
            for key, value in row.items()
        }


def get_first_value(row: Row, keys: Sequence[str]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return value
    return None


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
    direct = parse_pair(get_first_value(row, ("Satzpunkte",)))
    if direct:
        return direct
    ergebnis = get_first_value(row, ("Ergebnis",))
    if ergebnis and "/" in ergebnis:
        sets_part = ergebnis.split("/", 1)[0]
        direct = parse_pair(sets_part)
        if direct:
            return direct
    combined = get_first_value(row, ("Austragungsort/Ergebnis",))
    if combined and "/" in combined:
        sets_part = combined.split("/", 1)[0]
        direct = parse_pair(sets_part)
        if direct:
            return direct
    return None


def extract_points(row: Row) -> tuple[int, int] | None:
    points = parse_pair(get_first_value(row, ("Ballpunkte",)))
    if points:
        return points
    ergebnis = get_first_value(row, ("Ergebnis",))
    if ergebnis and "/" in ergebnis:
        _, points_part = ergebnis.split("/", 1)
        points = parse_pair(points_part)
        if points:
            return points
    combined = get_first_value(row, ("Austragungsort/Ergebnis",))
    if combined and "/" in combined:
        _, points_part = combined.split("/", 1)
        points = parse_pair(points_part)
        if points:
            return points
    return None


def extract_sets_text(row: Row) -> str | None:
    sets_pair = extract_sets(row)
    if not sets_pair:
        return None
    return f"{sets_pair[0]}:{sets_pair[1]}"


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


def parse_match_date(row: Row) -> str | None:
    combined_raw = get_first_value(row, ("Datum und Uhrzeit",))
    combined = (combined_raw or "").strip()
    if combined:
        for pattern in ("%d.%m.%Y, %H:%M:%S", "%d.%m.%Y, %H:%M"):
            try:
                return datetime.strptime(combined, pattern).date().isoformat()
            except ValueError:
                continue

    legacy_date = parse_date(get_first_value(row, ("Datum",)))
    if not legacy_date:
        return None

    # Legacy exports split date and time into separate columns.
    legacy_time_raw = get_first_value(row, ("Uhrzeit",))
    legacy_time = (legacy_time_raw or "").strip()
    if not legacy_time:
        return legacy_date
    for pattern in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(f"{legacy_date} {legacy_time}", f"%Y-%m-%d {pattern}").date().isoformat()
        except ValueError:
            continue
    return legacy_date


def clean_dict(data: MutableMapping[str, object]) -> Dict[str, object]:
    return {key: value for key, value in data.items() if value is not None}


def build_dataset(
    sources: Sequence[SeasonSource],
    *,
    home_team: str = _DEFAULT_HOME_TEAM,
) -> Dict[str, object]:
    seasons_payload: List[Dict[str, object]] = []
    for source in sources:
        opponents: Dict[str, Dict[str, object]] = {}
        seen_match_ids: set[str] = set()
        for url in source.urls:
            for row in fetch_csv_rows(url):
                team_home = row.get("Mannschaft 1") or ""
                team_away = row.get("Mannschaft 2") or ""
                if not (is_home_team(team_home, home_team) or is_home_team(team_away, home_team)):
                    continue
                sets_pair = extract_sets(row)
                if sets_pair is None:
                    continue
                match_identifier = (row.get("#") or "").strip()
                if match_identifier:
                    if match_identifier in seen_match_ids:
                        continue
                    seen_match_ids.add(match_identifier)

                home_is_configured = is_home_team(team_home, home_team)
                opponent_name = team_away if home_is_configured else team_home
                home_sets, opponent_sets = sets_pair if home_is_configured else (sets_pair[1], sets_pair[0])
                points_pair = extract_points(row)
                if points_pair:
                    home_points, opponent_points = (points_pair if home_is_configured else (points_pair[1], points_pair[0]))
                else:
                    home_points = opponent_points = None

                round_label = get_first_value(row, ("ST",))
                competition = get_first_value(row, ("Spielrunde",))
                date_iso = parse_match_date(row)
                location = get_first_value(row, ("Austragungsort",)) or None
                points_str = None
                if points_pair:
                    points_str = f"{points_pair[0]}:{points_pair[1]}"

                set_scores_pairs = extract_set_ballpoints(row)
                if home_is_configured:
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
                                "sets": row.get("Satzpunkte") or extract_sets_text(row),
                                "points": points_str,
                            }
                        ),
                        "home_sets": home_sets,
                        "opponent_sets": opponent_sets,
                        "home_points": home_points,
                        "opponent_points": opponent_points,
                        "home_won": home_sets > opponent_sets,
                    }
                )

                bucket = opponents.setdefault(
                    opponent_name,
                    {
                        "team": opponent_name,
                        "matches": [],
                        "summary": {
                            "matches_played": 0,
                            "home_wins": 0,
                            "opponent_wins": 0,
                            "home_sets_for": 0,
                            "opponent_sets_for": 0,
                            "home_points_for": 0,
                            "opponent_points_for": 0,
                        },
                    },
                )
                bucket["matches"].append(match_record)
                summary = bucket["summary"]
                summary["matches_played"] += 1
                if home_sets > opponent_sets:
                    summary["home_wins"] += 1
                else:
                    summary["opponent_wins"] += 1
                summary["home_sets_for"] += home_sets
                summary["opponent_sets_for"] += opponent_sets
                if home_points is not None and opponent_points is not None:
                    summary["home_points_for"] += home_points
                    summary["opponent_points_for"] += opponent_points
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
        "team": home_team,
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "seasons": seasons_payload,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Erzeuge eine JSON-Datei mit direkten Vergleichen aller Gegner des konfigurierten Heimteams.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Pfad für die erzeugte JSON-Datei (Standard: docs/data/direct_comparisons.json).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Pfad zur config.json (Standard: config.json im Repo-Root).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    _add_src_to_path()
    from usc_kommentatoren.config_loader import load_config

    args = parse_args(argv)
    cfg = load_config(args.config)
    dataset = build_dataset(SEASON_SOURCES, home_team=cfg.home_team)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
