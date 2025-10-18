"""Command line interface for aggregating Volleyball Bundesliga information."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from html import escape
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
        choices=["markdown", "json", "html"],
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
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional file path to write the rendered report to.",
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
            "league_matches": [serialize_match(match) for match in league_matches],
            "usc_matches": [serialize_match(match) for match in usc_matches],
            "articles": [asdict(article) for article in articles],
        }
        content = json.dumps(payload, indent=2, ensure_ascii=False)
    elif args.format == "html":
        content = render_html(
            standings=standings,
            league_matches=league_matches,
            usc_matches=usc_matches,
            articles=articles,
            limit=args.limit,
            next_games=args.next_games,
        )
    else:
        content = render_markdown(
            standings=standings,
            league_matches=league_matches,
            usc_matches=usc_matches,
            articles=articles,
            limit=args.limit,
            next_games=args.next_games,
        )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content)
    return 0


def render_markdown(
    *,
    standings: List[LeagueRanking],
    league_matches: List[LeagueMatch],
    usc_matches: List[LeagueMatch],
    articles: List[Article],
    limit: int,
    next_games: int,
) -> str:
    output_lines: List[str] = []
    if standings:
        output_lines.append("## Tabelle")
        output_lines.append(
            "| Platz | Team | Spiele | Siege | Niederlagen | Punkte | Satzquotient | Ballquotient |"
        )
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
        for match in sorted(league_matches, key=lambda item: item.date)[:limit]:
            output_lines.append(format_match_markdown(match))
        upcoming = sorted(league_matches, key=lambda item: item.date)[: args.limit]
        for match in upcoming:
            output_lines.append(format_match(match))
    else:
        output_lines.append("\n## Spielplan")
        output_lines.append("Keine Spieldaten verfügbar.")

    usc_future = future_usc_matches(usc_matches)
    if usc_future:
        output_lines.append("\n## Nächste Spiele USC Münster")
        for match in usc_future[:next_games]:
            output_lines.append(format_match_markdown(match))
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

    return "\n".join(output_lines)


def render_html(
    *,
    standings: List[LeagueRanking],
    league_matches: List[LeagueMatch],
    usc_matches: List[LeagueMatch],
    articles: List[Article],
    limit: int,
    next_games: int,
) -> str:
    lines: List[str] = [
        "<!DOCTYPE html>",
        '<html lang="de">',
        "<head>",
        '  <meta charset="utf-8" />',
        "  <title>USC Kommentatoren Report</title>",
        "  <style>",
        "    body { font-family: Arial, sans-serif; margin: 2rem; }",
        "    table { border-collapse: collapse; width: 100%; margin-bottom: 2rem; }",
        "    th, td { border: 1px solid #ccc; padding: 0.5rem; text-align: left; }",
        "    h1, h2, h3 { color: #134b96; }",
        "    ul { margin-bottom: 2rem; }",
        "  </style>",
        "</head>",
        "<body>",
        "  <h1>USC Kommentatoren Report</h1>",
        f"  <p>Stand: {escape(datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC'))}</p>",
    ]

    lines.append("  <h2>Tabelle</h2>")
    if standings:
        lines.append("  <table>")
        lines.append(
            "    <thead><tr><th>Platz</th><th>Team</th><th>Spiele</th><th>Siege</th><th>Niederlagen</th><th>Punkte</th><th>Satzquotient</th><th>Ballquotient</th></tr></thead>"
        )
        lines.append("    <tbody>")
        for row in standings:
            set_ratio = "-" if row.set_ratio is None else f"{row.set_ratio:.2f}"
            ball_ratio = "-" if row.ball_ratio is None else f"{row.ball_ratio:.2f}"
            lines.append(
                "      <tr><td>{rank}</td><td>{team}</td><td>{matches}</td><td>{wins}</td><td>{losses}</td><td>{points}</td><td>{set_ratio}</td><td>{ball_ratio}</td></tr>".format(
                    rank=escape(str(row.rank)),
                    team=escape(row.team_name),
                    matches=escape(str(row.matches_played)),
                    wins=escape(str(row.wins)),
                    losses=escape(str(row.losses)),
                    points=escape(str(row.points)),
                    set_ratio=escape(set_ratio),
                    ball_ratio=escape(ball_ratio),
                )
            )
        lines.append("    </tbody>")
        lines.append("  </table>")
    else:
        lines.append("  <p>Keine Tabellendaten verfügbar. Bitte API-Konfiguration prüfen.</p>")

    lines.append("  <h2>Spielplan</h2>")
    if league_matches:
        lines.append("  <ul>")
        for match in sorted(league_matches, key=lambda item: item.date)[:limit]:
            lines.append(f"    <li>{format_match_html(match)}</li>")
        lines.append("  </ul>")
    else:
        lines.append("  <p>Keine Spieldaten verfügbar.</p>")

    lines.append("  <h2>Nächste Spiele USC Münster</h2>")
    usc_future = future_usc_matches(usc_matches)
    if usc_future:
        lines.append("  <ul>")
        for match in usc_future[:next_games]:
            lines.append(f"    <li>{format_match_html(match)}</li>")
        lines.append("  </ul>")
    else:
        lines.append("  <p>Keine anstehenden Spiele verfügbar.</p>")

    lines.append("  <h2>Aktuelle Berichte</h2>")
    if articles:
        grouped = defaultdict(list)
        for article in articles:
            grouped[article.source].append(article)
        for source_name, items in grouped.items():
            lines.append(f"  <h3>{escape(source_name)}</h3>")
            lines.append("  <ul>")
            for entry in items:
                lines.append(
                    "    <li><a href=\"{link}\">{title}</a></li>".format(
                        link=escape(entry.link, quote=True),
                        title=escape(entry.title),
                    )
                )
            lines.append("  </ul>")
    else:
        lines.append("  <p>Keine Artikel gefunden.</p>")

    lines.append("</body>")
    lines.append("</html>")
    return "\n".join(lines)


def format_match_markdown(match: LeagueMatch) -> str:
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


def format_match_html(match: LeagueMatch) -> str:
    date_str = match.date.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    parts = [
        f"{escape(date_str)}: {escape(match.team_home)} vs. {escape(match.team_away)}",
    ]
    if match.venue:
        parts.append(f" (Spielort: {escape(match.venue)})")
    if match.results:
        parts.append(f" – Ergebnis: {escape(match.results)}")
    return "".join(parts)


def serialize_match(match: LeagueMatch) -> dict:
    return {
        "uuid": match.uuid,
        "date": match.date.isoformat(),
        "team_home": match.team_home,
        "team_away": match.team_away,
        "venue": match.venue,
        "results": match.results,
    }


def future_usc_matches(matches: List[LeagueMatch]) -> List[LeagueMatch]:
    return [m for m in sorted(matches, key=lambda item: item.date) if m.date >= datetime.now(timezone.utc)]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
