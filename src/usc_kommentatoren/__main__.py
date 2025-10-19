from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .report import (
    DEFAULT_SCHEDULE_URL,
    NEWS_LOOKBACK_DAYS,
    USC_CANONICAL_NAME,
    build_html_report,
    collect_instagram_links,
    collect_team_roster,
    collect_team_news,
    collect_team_photo,
    collect_team_transfers,
    download_schedule,
    find_last_matches_for_team,
    find_next_usc_home_match,
    load_schedule_from_file,
)

DEFAULT_OUTPUT_PATH = Path("docs/index.html")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate USC Münster schedule report")
    parser.add_argument(
        "--schedule-url",
        default=DEFAULT_SCHEDULE_URL,
        help="CSV export URL of the Volleyball Bundesliga schedule.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Target HTML file path (default: docs/index.html).",
    )
    parser.add_argument(
        "--app-output",
        type=Path,
        default=Path("docs/index_app.html"),
        help="Pfad für die App-optimierte HTML-Version (Standard: docs/index_app.html).",
    )
    parser.add_argument(
        "--app-scale",
        type=float,
        default=0.75,
        help="Schriftgrößenfaktor für die App-Version (Standard: 0.75).",
    )
    parser.add_argument(
        "--skip-app-output",
        action="store_true",
        help="App-optimierte HTML-Datei nicht erzeugen.",
    )
    parser.add_argument(
        "--schedule-path",
        type=Path,
        default=Path("data/schedule.csv"),
        help="Local path to store the downloaded schedule CSV.",
    )
    parser.add_argument(
        "--roster-dir",
        type=Path,
        default=Path("data/rosters"),
        help="Local directory to persist downloaded roster CSV exports (default: data/rosters).",
    )
    parser.add_argument(
        "--photo-dir",
        type=Path,
        default=Path("data/team_photos"),
        help="Local directory to cache downloaded team photos (default: data/team_photos).",
    )
    parser.add_argument(
        "--recent-limit",
        type=int,
        default=2,
        help="Number of previous matches to include per team (default: 2).",
    )
    parser.add_argument(
        "--public-url",
        help="Optional öffentliche URL, unter der der Bericht erreichbar sein wird.",
    )
    parser.add_argument(
        "--news-lookback",
        type=int,
        default=NEWS_LOOKBACK_DAYS,
        help="Anzahl der Tage, aus denen News berücksichtigt werden (Standard: 14).",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    download_schedule(
        args.schedule_path,
        url=args.schedule_url,
    )
    matches = load_schedule_from_file(args.schedule_path)
    next_home = find_next_usc_home_match(matches)
    if not next_home:
        raise SystemExit("Kein zukünftiges Heimspiel des USC Münster gefunden.")

    usc_recent = find_last_matches_for_team(matches, USC_CANONICAL_NAME, limit=args.recent_limit)
    opponent_recent = find_last_matches_for_team(matches, next_home.away_team, limit=args.recent_limit)

    usc_news, opponent_news = collect_team_news(
        next_home,
        lookback_days=args.news_lookback,
    )

    usc_instagram = collect_instagram_links(USC_CANONICAL_NAME)
    opponent_instagram = collect_instagram_links(next_home.away_team)

    try:
        usc_roster = collect_team_roster(USC_CANONICAL_NAME, args.roster_dir)
    except Exception as exc:  # pragma: no cover - network failure
        print(
            f"Warnung: Kader für {USC_CANONICAL_NAME} konnte nicht geladen werden: {exc}",
            file=sys.stderr,
        )
        usc_roster = []
    try:
        opponent_roster = collect_team_roster(next_home.away_team, args.roster_dir)
    except Exception as exc:  # pragma: no cover - network failure
        print(
            f"Warnung: Kader für {next_home.away_team} konnte nicht geladen werden: {exc}",
            file=sys.stderr,
        )
        opponent_roster = []

    try:
        usc_transfers = collect_team_transfers(USC_CANONICAL_NAME)
    except Exception as exc:  # pragma: no cover - network failure
        print(
            f"Warnung: Wechselbörse für {USC_CANONICAL_NAME} konnte nicht geladen werden: {exc}",
            file=sys.stderr,
        )
        usc_transfers = []
    try:
        opponent_transfers = collect_team_transfers(next_home.away_team)
    except Exception as exc:  # pragma: no cover - network failure
        print(
            f"Warnung: Wechselbörse für {next_home.away_team} konnte nicht geladen werden: {exc}",
            file=sys.stderr,
        )
        opponent_transfers = []

    try:
        usc_photo = collect_team_photo(USC_CANONICAL_NAME, args.photo_dir)
    except Exception as exc:  # pragma: no cover - network failure
        print(
            f"Warnung: Teamfoto für {USC_CANONICAL_NAME} konnte nicht geladen werden: {exc}",
            file=sys.stderr,
        )
        usc_photo = None
    try:
        opponent_photo = collect_team_photo(next_home.away_team, args.photo_dir)
    except Exception as exc:  # pragma: no cover - network failure
        print(
            f"Warnung: Teamfoto für {next_home.away_team} konnte nicht geladen werden: {exc}",
            file=sys.stderr,
        )
        opponent_photo = None

    report_kwargs = dict(
        next_home=next_home,
        usc_recent=usc_recent,
        opponent_recent=opponent_recent,
        usc_news=usc_news,
        opponent_news=opponent_news,
        usc_instagram=usc_instagram,
        opponent_instagram=opponent_instagram,
        usc_roster=usc_roster,
        opponent_roster=opponent_roster,
        usc_transfers=usc_transfers,
        opponent_transfers=opponent_transfers,
        usc_photo=usc_photo,
        opponent_photo=opponent_photo,
        public_url=args.public_url,
    )

    html = build_html_report(**report_kwargs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")

    if not args.skip_app_output and args.app_output:
        app_html = build_html_report(font_scale=args.app_scale, **report_kwargs)
        args.app_output.parent.mkdir(parents=True, exist_ok=True)
        args.app_output.write_text(app_html, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
