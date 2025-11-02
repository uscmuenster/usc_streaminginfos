from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from .mvp import collect_mvp_rankings
from .report import (
    DEFAULT_SCHEDULE_URL,
    NEWS_LOOKBACK_DAYS,
    USC_CANONICAL_NAME,
    BERLIN_TZ,
    THEME_COLORS,
    build_html_report,
    collect_instagram_links,
    collect_match_stats_totals,
    collect_team_roster,
    collect_team_news,
    collect_team_photo,
    collect_team_transfers,
    enrich_match,
    enrich_matches,
    fetch_schedule_match_metadata,
    download_schedule,
    find_last_matches_for_team,
    find_next_match_for_team,
    find_next_usc_home_match,
    is_usc,
    load_schedule_from_file,
    prepare_direct_comparison,
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
        "--mvp-output",
        type=Path,
        default=Path("docs/data/mvp_rankings.json"),
        help="Pfad zur JSON-Datei mit MVP-Rankings (Standard: docs/data/mvp_rankings.json).",
    )
    parser.add_argument(
        "--skip-mvp-output",
        action="store_true",
        help="MVP-Ranking-Datei nicht erzeugen.",
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
        "--season-results",
        type=Path,
        default=Path("docs/data/season_results_2024_25.json"),
        help="Pfad zur JSON-Datei mit den Saisonergebnissen (Standard: docs/data/season_results_2024_25.json).",
    )
    parser.add_argument(
        "--direct-comparisons",
        type=Path,
        default=Path("docs/data/direct_comparisons.json"),
        help="Pfad zur JSON-Datei mit direkten Vergleichen (Standard: docs/data/direct_comparisons.json).",
    )
    parser.add_argument(
        "--recent-limit",
        type=int,
        default=4,
        help="Number of previous matches to include per team (default: 4).",
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
    try:
        schedule_metadata = fetch_schedule_match_metadata()
    except Exception as exc:  # pragma: no cover - network failure
        print(
            f"Warnung: Match-Metadaten konnten nicht geladen werden: {exc}",
            file=sys.stderr,
        )
        schedule_metadata = {}
    next_home = find_next_usc_home_match(matches)
    if not next_home:
        raise SystemExit("Kein zukünftiges Heimspiel des USC Münster gefunden.")

    reference_time = next_home.kickoff + timedelta(seconds=1)
    usc_next = find_next_match_for_team(
        matches,
        USC_CANONICAL_NAME,
        reference=reference_time,
    )
    opponent_next = find_next_match_for_team(
        matches,
        next_home.away_team,
        reference=reference_time,
    )

    usc_upcoming_matches: List["Match"] = []
    if usc_next:
        usc_upcoming_matches.append(usc_next)
        if not is_usc(usc_next.host):
            additional_home = find_next_usc_home_match(
                matches,
                reference=usc_next.kickoff + timedelta(seconds=1),
            )
            if (
                additional_home
                and not any(
                    match.kickoff == additional_home.kickoff
                    and match.home_team == additional_home.home_team
                    and match.away_team == additional_home.away_team
                    for match in usc_upcoming_matches
                )
            ):
                usc_upcoming_matches.append(additional_home)

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

    season_results_data = None
    if args.season_results:
        try:
            season_results_data = json.loads(
                args.season_results.read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            print(
                f"Hinweis: Saisonübersicht {args.season_results} wurde nicht gefunden.",
                file=sys.stderr,
            )
        except Exception as exc:  # pragma: no cover - invalid JSON
            print(
                f"Warnung: Saisonübersicht konnte nicht geladen werden: {exc}",
                file=sys.stderr,
            )
            season_results_data = None

    direct_comparisons_payload = None
    if args.direct_comparisons:
        try:
            direct_comparisons_payload = json.loads(
                args.direct_comparisons.read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            print(
                f"Hinweis: Direkter Vergleich {args.direct_comparisons} wurde nicht gefunden.",
                file=sys.stderr,
            )
        except Exception as exc:  # pragma: no cover - invalid JSON
            print(
                f"Warnung: Direkter Vergleich konnte nicht geladen werden: {exc}",
                file=sys.stderr,
            )
            direct_comparisons_payload = None

    mvp_rankings_data: Optional[Dict[str, Dict[str, List[List[str]]]]] = None

    if args.mvp_output and not args.skip_mvp_output:
        try:
            mvp_rankings = collect_mvp_rankings(
                [next_home.away_team, USC_CANONICAL_NAME]
            )
        except Exception as exc:  # pragma: no cover - network failure
            print(
                f"Warnung: MVP-Rankings konnten nicht geladen werden: {exc}",
                file=sys.stderr,
            )
        else:
            mvp_rankings_data = mvp_rankings
            args.mvp_output.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(mvp_rankings, ensure_ascii=False, indent=2)
            args.mvp_output.write_text(payload + "\n", encoding="utf-8")

    detail_cache: Dict[str, Dict[str, object]] = {}
    next_home = enrich_match(next_home, schedule_metadata, detail_cache)
    usc_recent = enrich_matches(usc_recent, schedule_metadata, detail_cache)
    opponent_recent = enrich_matches(opponent_recent, schedule_metadata, detail_cache)
    if usc_upcoming_matches:
        usc_upcoming_matches = [
            enrich_match(match, schedule_metadata, detail_cache)
            for match in usc_upcoming_matches
        ]
        usc_upcoming_matches.sort(key=lambda match: match.kickoff)
    if opponent_next:
        opponent_next = enrich_match(opponent_next, schedule_metadata, detail_cache)

    generated_at = datetime.now(tz=BERLIN_TZ)

    stats_matches: List[Match] = []
    stats_matches.extend(usc_recent)
    stats_matches.extend(opponent_recent)
    match_stats_map = collect_match_stats_totals(stats_matches)

    direct_comparison_data = prepare_direct_comparison(
        direct_comparisons_payload,
        next_home.away_team,
    )

    report_kwargs = dict(
        next_home=next_home,
        usc_recent=usc_recent,
        opponent_recent=opponent_recent,
        usc_upcoming=tuple(usc_upcoming_matches),
        opponent_next=opponent_next,
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
        season_results=season_results_data,
        generated_at=generated_at,
        match_stats=match_stats_map,
        mvp_rankings=mvp_rankings_data,
        direct_comparison=direct_comparison_data,
    )

    html = build_html_report(**report_kwargs)
    output_dir = args.output.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")

    app_relative: Optional[str] = None
    if not args.skip_app_output and args.app_output:
        app_html = build_html_report(font_scale=args.app_scale, **report_kwargs)
        args.app_output.parent.mkdir(parents=True, exist_ok=True)
        args.app_output.write_text(app_html, encoding="utf-8")
        try:
            app_relative = args.app_output.relative_to(output_dir).as_posix()
        except ValueError:
            app_relative = args.app_output.name

    output_relative = args.output.relative_to(output_dir).as_posix()

    manifest_path = output_dir / "manifest.webmanifest"
    start_url = f"./{app_relative}" if app_relative else f"./{output_relative}"
    manifest_payload = {
        "name": "USC Streaminginfos",
        "short_name": "USC Infos",
        "description": "Aktuelle Informationen und Statistiken zu USC Münster.",
        "lang": "de",
        "start_url": start_url,
        "scope": "./",
        "display": "standalone",
        "background_color": THEME_COLORS["mvp_overview_summary_bg"],
        "theme_color": THEME_COLORS["mvp_overview_summary_bg"],
        "orientation": "portrait-primary",
        "icons": [
            {
                "src": "favicon.png",
                "sizes": "192x192",
                "type": "image/png",
            },
            {
                "src": "favicon.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    offline_urls = [
        "./",
        f"./{output_relative}",
        "./favicon.png",
        "./manifest.webmanifest",
    ]
    if app_relative:
        offline_urls.append(f"./{app_relative}")

    offline_urls_literal = ",\n        ".join(f'"{item}"' for item in offline_urls)
    sw_path = output_dir / "sw.js"
    sw_script = f"""const CACHE_NAME = 'usc-streaminginfos-v1';
const OFFLINE_URLS = [
        {offline_urls_literal}
];
const FALLBACK_URL = './{output_relative}';

self.addEventListener('install', (event) => {{
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(OFFLINE_URLS))
      .catch(() => undefined)
  );
}});

self.addEventListener('activate', (event) => {{
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
}});

self.addEventListener('fetch', (event) => {{
  if (event.request.method !== 'GET') {{
    return;
  }}

  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {{
      if (cachedResponse) {{
        return cachedResponse;
      }}

      return fetch(event.request).catch(() => caches.match(FALLBACK_URL));
    }})
  );
}});
"""
    sw_path.write_text(sw_script, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
