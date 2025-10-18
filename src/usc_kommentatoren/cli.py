"""Command line interface for aggregating Volleyball Bundesliga information."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List

from .config import AppConfig, NewsSource, load_config
from .news import Article, gather_articles
from .vbl import LeagueMatch, LeagueRanking, VblApi


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect standings, schedules, and news for the Volleyball Bundesliga women."
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to the YAML configuration file.",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of league matches to display.",
    )
    parser.add_argument(
        "--next-games",
        type=int,
        default=5,
        help="Number of upcoming USC Münster matches to display.",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = load_config(args.config)

    standings: List[LeagueRanking] = []
    league_matches: List[LeagueMatch] = []
    usc_matches: List[LeagueMatch] = []

    if config.api and config.api.api_key and config.api.league_uuid:
        api = VblApi(config.api.api_key)
        if config.api.league_uuid:
            standings = api.get_league_rankings(config.api.league_uuid)
            league_matches = api.get_league_matches(config.api.league_uuid)
        if config.api.team_uuid:
            usc_matches = api.get_team_matches(config.api.team_uuid)
    else:
        print("⚠️  Kein API-Schlüssel angegeben – Tabellen- und Spielplandaten werden übersprungen.", file=sys.stderr)

    articles: List[Article] = gather_articles(config.news_sources)

    if args.format == "json":
        payload = {
            "standings": [asdict(rank) for rank in standings],
            "league_matches": [
                {
                    "uuid": match.uuid,
                    "date": match.date.isoformat(),
                    "team_home": match.team_home,
                    "team_away": match.team_away,
                    "venue": match.venue,
                    "results": match.results,
                }
                for match in league_matches
            ],
            "usc_matches": [
                {
                    "uuid": match.uuid,
                    "date": match.date.isoformat(),
                    "team_home": match.team_home,
                    "team_away": match.team_away,
                    "venue": match.venue,
                    "results": match.results,
                }
                for match in usc_matches
            ],
            "articles": [asdict(article) for article in articles],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    output_lines: List[str] = []
    if standings:
        output_lines.append("## Tabelle")
        output_lines.append("| Platz | Team | Spiele | Siege | Niederlagen | Punkte | Satzquotient | Ballquotient |")
        output_lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for row in standings:
            set_ratio = "-" if row.set_ratio is None else f"{row.set_ratio:.2f}"
            ball_ratio = "-" if row.ball_ratio is None else f"{row.ball_ratio:.2f}"
            output_lines.append(
                "| {rank} | {team} | {matches} | {wins} | {losses} | {points} | {set_ratio} | {ball_ratio} |".format(
                    rank=row.rank,
                    team=row.team_name,
                    matches=row.matches_played,
                    wins=row.wins,
                    losses=row.losses,
                    points=row.points,
                    set_ratio=set_ratio,
                    ball_ratio=ball_ratio,
                )
            )
    else:
        output_lines.append("## Tabelle")
        output_lines.append("Keine Tabellendaten verfügbar. Bitte API-Konfiguration prüfen.")

    if league_matches:
        output_lines.append("\n## Spielplan")
        upcoming = sorted(league_matches, key=lambda item: item.date)[: args.limit]
        for match in upcoming:
            output_lines.append(format_match(match))
    else:
        output_lines.append("\n## Spielplan")
        output_lines.append("Keine Spieldaten verfügbar.")

    if usc_matches:
        output_lines.append("\n## Nächste Spiele USC Münster")
        future_matches = [m for m in sorted(usc_matches, key=lambda item: item.date) if m.date >= datetime.now(timezone.utc)]
        for match in future_matches[: args.next_games]:
            output_lines.append(format_match(match))
        if not future_matches:
            output_lines.append("Keine anstehenden Spiele gefunden.")
    else:
        output_lines.append("\n## Nächste Spiele USC Münster")
        output_lines.append("Keine anstehenden Spiele verfügbar.")

    if articles:
        output_lines.append("\n## Aktuelle Berichte")
        grouped = defaultdict(list)
        for article in articles:
            grouped[article.source].append(article)
        for source_name, items in grouped.items():
            output_lines.append(f"### {source_name}")
            for entry in items:
                output_lines.append(f"- [{entry.title}]({entry.link})")
    else:
        output_lines.append("\n## Aktuelle Berichte")
        output_lines.append("Keine Artikel gefunden.")

    print("\n".join(output_lines))
    return 0


def format_match(match: LeagueMatch) -> str:
    date_str = match.date.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    parts = [f"- {date_str}: {match.team_home} vs. {match.team_away}"]
    if match.venue:
        parts.append(f" (Spielort: {match.venue})")
    if match.results:
        parts.append(f" – Ergebnis: {match.results}")
    return "".join(parts)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
