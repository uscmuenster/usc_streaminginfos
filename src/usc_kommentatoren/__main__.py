from __future__ import annotations

import argparse
from pathlib import Path

from .report import (
    DEFAULT_SCHEDULE_URL,
    NEWS_LOOKBACK_DAYS,
    USC_CANONICAL_NAME,
    build_html_report,
    collect_instagram_links,
    collect_team_news,
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
        "--schedule-path",
        type=Path,
        default=Path("data/schedule.csv"),
        help="Local path to store the downloaded schedule CSV.",
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

    html = build_html_report(
        next_home=next_home,
        usc_recent=usc_recent,
        opponent_recent=opponent_recent,
        usc_news=usc_news,
        opponent_news=opponent_news,
        usc_instagram=usc_instagram,
        opponent_instagram=opponent_instagram,
        public_url=args.public_url,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
