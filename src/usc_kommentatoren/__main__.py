from __future__ import annotations

import argparse
from pathlib import Path

from .report import (
    DEFAULT_SCHEDULE_URL,
    USC_CANONICAL_NAME,
    build_html_report,
    download_schedule,
    find_last_matches_for_team,
    find_next_usc_home_match,
    load_schedule_from_file,
)


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
        required=True,
        help="Target HTML file path.",
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

    html = build_html_report(next_home=next_home, usc_recent=usc_recent, opponent_recent=opponent_recent)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
