#!/usr/bin/env python3
"""Generate docs/internationale_spiele.html with international match overview."""

from __future__ import annotations

import html
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, MutableMapping, Sequence

import requests
from bs4 import BeautifulSoup

OUTPUT_PATH = Path("docs/internationale_spiele.html")
USER_AGENT = {"User-Agent": "Mozilla/5.0 (compatible; usc-streaminginfos-bot/2.0)"}


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    stripped = "".join(char for char in normalized if not unicodedata.combining(char))
    return stripped.casefold()


@dataclass(frozen=True)
class TeamConfig:
    name: str
    aliases: Sequence[str] = ()

    def matches(self, candidate: str) -> bool:
        candidate_norm = _normalize(candidate)
        if candidate_norm == _normalize(self.name):
            return True
        return any(candidate_norm == _normalize(alias) for alias in self.aliases)


@dataclass(frozen=True)
class CompetitionConfig:
    title: str
    landing_page: str
    teams: Sequence[TeamConfig]


COMPETITIONS: Sequence[CompetitionConfig] = (
    CompetitionConfig(
        title="CEV Champions League Volley 2025/26 (Frauen)",
        landing_page="https://championsleague.cev.eu/en/women/",
        teams=(
            TeamConfig("DRESDNER SC"),
            TeamConfig("SSC Palmberg SCHWERIN"),
        ),
    ),
    CompetitionConfig(
        title="CEV Volleyball Cup 2025/26 (Frauen)",
        landing_page="https://www.cev.eu/club/volleyball-cup/2026/women/",
        teams=(
            TeamConfig("Allianz MTV STUTTGART"),
            TeamConfig(
                "VfB SUHL Thüringen",
                aliases=("VfB Suhl LOTTO Thüringen", "VfB Suhl LOTTO Thuringen"),
            ),
        ),
    ),
    CompetitionConfig(
        title="CEV Volleyball Challenge Cup 2025/26 (Frauen)",
        landing_page="https://www.cev.eu/club/volleyball-challenge-cup/2026/women/",
        teams=(TeamConfig("SC POTSDAM"),),
    ),
)


MatchRecord = MutableMapping[str, object]


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=USER_AGENT, timeout=30)
    resp.raise_for_status()
    return resp.text


def fetch_json(url: str) -> Dict:
    resp = requests.get(url, headers=USER_AGENT, timeout=30)
    resp.raise_for_status()
    return resp.json()


def discover_score_endpoints(landing_page: str) -> List[str]:
    html_text = fetch_html(landing_page)
    soup = BeautifulSoup(html_text, "html.parser")
    endpoints: List[str] = []
    seen = set()
    for element in soup.select("[data-score-endpoint]"):
        raw = element.get("data-score-endpoint")
        if not raw:
            continue
        if raw.startswith("//"):
            url = f"https:{raw}"
        elif raw.startswith("/"):
            url = f"https://www.cev.eu{raw}"
        else:
            url = raw
        if url not in seen:
            endpoints.append(url)
            seen.add(url)
    return endpoints


def parse_match_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    if value.startswith("1900") or value.startswith("2100"):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def update_record(base: MatchRecord, new_values: MatchRecord) -> None:
    for key, value in new_values.items():
        if value in (None, ""):
            continue
        if key not in base or base[key] in (None, ""):
            base[key] = value
        elif key == "is_complete" and value:
            base[key] = True


def collect_matches(comp: CompetitionConfig) -> Dict[str, List[MatchRecord]]:
    endpoints = discover_score_endpoints(comp.landing_page)
    matches_by_team: Dict[str, Dict[int, MatchRecord]] = {
        cfg.name: {} for cfg in comp.teams
    }

    for endpoint in endpoints:
        payload = fetch_json(endpoint)
        for pool in payload.get("Pools", []):
            phase_name = pool.get("Name") or ""
            for match in pool.get("Results", []):
                match_id = match.get("MatchId")
                if not match_id:
                    continue
                phase = match.get("PhaseName") or phase_name
                leg = match.get("LegName") or ""
                raw_timestamp = match.get("MatchDateTime") or ""
                match_dt = parse_match_datetime(raw_timestamp)
                if raw_timestamp.startswith(("1900", "2100")):
                    raw_timestamp = ""
                match_url = match.get("MatchCentreUrl") or ""
                location = match.get("Location") or ""
                stadium = match.get("Stadium") or ""
                sets_formatted = match.get("SetsFormatted") or ""
                is_complete = bool(match.get("IsComplete"))

                for side_key in ("HomeTeam", "AwayTeam"):
                    team_data = match.get(side_key) or {}
                    team_name = team_data.get("Name") or ""
                    if not team_name:
                        continue
                    matched_cfg = next((cfg for cfg in comp.teams if cfg.matches(team_name)), None)
                    if not matched_cfg:
                        continue
                    opponent_key = "AwayTeam" if side_key == "HomeTeam" else "HomeTeam"
                    opponent_data = match.get(opponent_key) or {}
                    opponent_name = opponent_data.get("Name") or "Unbekannter Gegner"
                    if _normalize(opponent_name) == _normalize("Bye"):
                        continue

                    record: MatchRecord = {
                        "match_id": match_id,
                        "phase": phase,
                        "leg": leg,
                        "date": match_dt,
                        "raw_date": raw_timestamp,
                        "location": location,
                        "stadium": stadium,
                        "match_url": match_url,
                        "sets_formatted": sets_formatted,
                        "is_complete": is_complete,
                        "is_home": side_key == "HomeTeam",
                        "opponent": opponent_name,
                        "opponent_nation": opponent_data.get("NationName") or "",
                        "our_sets": team_data.get("Score"),
                        "opponent_sets": opponent_data.get("Score"),
                    }

                    team_records = matches_by_team[matched_cfg.name]
                    existing = team_records.get(match_id)
                    if existing:
                        update_record(existing, record)
                    else:
                        team_records[match_id] = record

    return {
        team: sorted(records.values(), key=lambda item: (
            item["date"] if item["date"] is not None else datetime.max,
            item["match_id"],
        ))
        for team, records in matches_by_team.items()
    }


def format_match_row(match: MatchRecord) -> str:
    is_complete = bool(match.get("is_complete"))
    opponent_raw = str(match.get("opponent", "Unbekannter Gegner"))
    opponent_display = html.escape(opponent_raw)
    opponent_nation = match.get("opponent_nation") or ""
    if opponent_nation:
        opponent_display = f"{opponent_display} ({html.escape(opponent_nation)})"

    if match.get("is_home"):
        pairing_html = f"Heimspiel gegen {opponent_display}"
    else:
        pairing_html = f"Auswärtsspiel bei {opponent_display}"

    phase_parts = [value for value in (match.get("phase"), match.get("leg")) if value]
    header = " · ".join(html.escape(part) for part in phase_parts) if phase_parts else "Wettbewerbsphase noch offen"

    date = match.get("date")
    if isinstance(date, datetime):
        date_text = date.strftime("%d.%m.%Y %H:%M Uhr (CEV-Angabe)")
    else:
        raw_date = match.get("raw_date") or ""
        date_text = "Termin noch nicht festgelegt" if not raw_date else f"Termin laut CEV: {html.escape(raw_date)}"

    location_parts = []
    if match.get("stadium"):
        location_parts.append(html.escape(str(match["stadium"])))
    if match.get("location") and match["location"] != match.get("stadium"):
        location_parts.append(html.escape(str(match["location"])))
    location_text = " · ".join(location_parts)

    score_text = ""
    if is_complete:
        our_sets = match.get("our_sets")
        opp_sets = match.get("opponent_sets")
        if our_sets is not None and opp_sets is not None:
            score_text = f"Sätze: {our_sets}:{opp_sets}"
        sets_formatted = match.get("sets_formatted") or ""
        if sets_formatted:
            formatted = html.escape(sets_formatted)
            score_text = f"{score_text} – {formatted}" if score_text else formatted
    else:
        score_text = "Noch nicht gespielt"

    meta_parts = [html.escape(date_text)]
    if location_text:
        meta_parts.append(location_text)
    match_url = match.get("match_url") or ""
    if match_url:
        meta_parts.append(f"<a href=\"{html.escape(match_url)}\" rel=\"noopener\" target=\"_blank\">Match-Centre</a>")

    meta_html = " | ".join(meta_parts)

    return (
        "      <li class=\"match-card\">\n"
        "        <div class=\"match-header\">{header}</div>\n"
        f"        <div class=\"match-pairing\">{pairing_html}</div>\n"
        "        <div class=\"match-score\">{score}</div>\n"
        f"        <div class=\"match-meta\">{meta_html}</div>\n"
        "      </li>"
    ).format(header=header or "", score=html.escape(score_text))


def render_team_section(team: str, matches: Iterable[MatchRecord]) -> str:
    completed: List[MatchRecord] = []
    upcoming: List[MatchRecord] = []
    for match in matches:
        if match.get("is_complete"):
            completed.append(match)
        else:
            upcoming.append(match)

    def render_group(title: str, items: List[MatchRecord]) -> str:
        heading = html.escape(title)
        if not items:
            return (
                "    <details class=\"match-group\">\n"
                f"      <summary>{heading}</summary>\n"
                "      <div class=\"match-content\">\n"
                "        <p class=\"group-empty\">Keine Einträge vorhanden.</p>\n"
                "      </div>\n"
                "    </details>"
            )
        rows = "\n".join(format_match_row(item) for item in items)
        return (
            "    <details class=\"match-group\">\n"
            f"      <summary>{heading}</summary>\n"
            "      <div class=\"match-content\">\n"
            "        <ul class=\"match-list\">\n"
            f"{rows}\n"
            "        </ul>\n"
            "      </div>\n"
            "    </details>"
        )

    upcoming_sorted = sorted(upcoming, key=lambda item: (
        item["date"] if item.get("date") is not None else datetime.max,
        item["match_id"],
    ))
    completed_sorted = sorted(completed, key=lambda item: (
        item["date"] if item.get("date") is not None else datetime.min,
        item["match_id"],
    ), reverse=True)

    groups = [
        render_group("Anstehende Spiele", upcoming_sorted),
        render_group("Abgeschlossene Spiele", completed_sorted),
    ]
    groups_html = "\n".join(groups)
    groups_html_indented = "\n".join(
        f"      {line}" for line in groups_html.splitlines()
    )

    upcoming_count = len(upcoming_sorted)
    completed_count = len(completed_sorted)
    summary_segments: List[str] = []
    if upcoming_count:
        summary_segments.append(
            f"{upcoming_count} anstehend"
        )
    if completed_count:
        summary_segments.append(
            f"{completed_count} abgeschlossen"
        )
    if not summary_segments:
        summary_segments.append("Keine gemeldeten Spiele")
    summary_text = " · ".join(summary_segments)

    open_attr = " open" if upcoming_count else ""

    return (
        f"  <details class=\"team-section\"{open_attr}>\n"
        "    <summary>\n"
        f"      <span class=\"team-name\">{html.escape(team)}</span>\n"
        f"      <span class=\"team-meta\">{html.escape(summary_text)}</span>\n"
        "    </summary>\n"
        "    <div class=\"team-section-content\">\n"
        f"{groups_html_indented}\n"
        "    </div>\n"
        "  </details>"
    )


def render_html(comp_results: List[tuple[CompetitionConfig, Dict[str, List[MatchRecord]]]]) -> str:
    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M Uhr")
    competition_blocks = []
    for comp, teams in comp_results:
        team_sections = "\n".join(
            render_team_section(team_name, matches) for team_name, matches in teams.items()
        )
        competition_blocks.append(
            "  <section class=\"competition\">\n"
            f"    <h2>{html.escape(comp.title)}</h2>\n"
            f"    <p class=\"competition-source\">Quelle: <a href=\"{html.escape(comp.landing_page)}\" rel=\"noopener\" target=\"_blank\">Offizielle CEV-Wettbewerbsseite</a></p>\n"
            f"{team_sections}\n"
            "  </section>"
        )

    competitions_html = "\n".join(competition_blocks)

    return f"""<!DOCTYPE html>
<html lang=\"de\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Internationale Spiele deutscher Frauen-Teams</title>
  <style>
    :root {{
      color-scheme: light dark;
      --font-scale: 1;
      --bg: #f8fafc;
      --text: #1f2937;
      --accent: #004c54;
      --card-bg: #ffffff;
      --card-shadow: rgba(15, 23, 42, 0.12);
      --border: rgba(148, 163, 184, 0.4);
    }}
    body {{
      margin: 0;
      font-family: "Inter", "Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      font-size: calc(var(--font-scale) * clamp(0.95rem, 1.8vw, 1.05rem));
      line-height: 1.6;
    }}
    main {{
      max-width: 68rem;
      margin: 0 auto;
      padding: clamp(1rem, 4vw, 2.75rem);
    }}
    header {{
      display: flex;
      flex-direction: column;
      gap: clamp(0.6rem, 2vw, 1rem);
      margin-bottom: clamp(1.1rem, 3vw, 1.7rem);
    }}
    header nav {{
      margin-bottom: clamp(0.2rem, 1vw, 0.5rem);
    }}
    header nav a {{
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      text-decoration: none;
      color: var(--accent);
      font-weight: 600;
      background: #ecfdf5;
      padding: 0.4rem 0.75rem;
      border-radius: 999px;
      transition: background 0.2s ease, color 0.2s ease;
    }}
    header nav a:hover,
    header nav a:focus-visible {{
      background: var(--accent);
      color: #ffffff;
      outline: none;
    }}
    h1 {{
      margin-top: 0;
      margin-bottom: 0.75rem;
      font-size: calc(var(--font-scale) * clamp(1.8rem, 4.8vw, 2.65rem));
      color: var(--accent);
    }}
    h2 {{
      margin: clamp(1.5rem, 4vw, 2.25rem) 0 clamp(0.75rem, 2vw, 1.25rem) 0;
      font-size: calc(var(--font-scale) * clamp(1.3rem, 3.6vw, 1.75rem));
    }}
    h3 {{
      margin: clamp(0.85rem, 2.4vw, 1.6rem) 0 clamp(0.6rem, 1.8vw, 1.1rem) 0;
      font-size: calc(var(--font-scale) * clamp(1.1rem, 2.8vw, 1.45rem));
    }}
    h4 {{
      margin: clamp(0.5rem, 1.6vw, 0.9rem) 0;
      font-size: calc(var(--font-scale) * clamp(1rem, 2.4vw, 1.2rem));
    }}
    .meta {{
      font-size: calc(var(--font-scale) * 0.9rem);
      color: #475569;
      margin-bottom: clamp(1.1rem, 3vw, 1.7rem);
    }}
    .competition {{
      background: var(--card-bg);
      border-radius: 1rem;
      padding: clamp(1.25rem, 3vw, 1.85rem);
      box-shadow: 0 14px 32px var(--card-shadow);
      margin-bottom: clamp(1.5rem, 4vw, 2.5rem);
    }}
    .competition-source a {{
      color: #0f766e;
      text-decoration: none;
      font-weight: 600;
    }}
    .competition-source a:hover,
    .competition-source a:focus-visible {{
      text-decoration: underline;
      outline: none;
    }}
    .team-section {{
      margin-top: clamp(1rem, 3vw, 1.5rem);
      border: 1px solid var(--border);
      border-radius: 1rem;
      background: #f8fafc;
      box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08);
      overflow: hidden;
    }}
    .team-section:first-of-type {{
      margin-top: clamp(0.75rem, 2.4vw, 1.1rem);
    }}
    .team-section summary {{
      cursor: pointer;
      list-style: none;
      display: flex;
      align-items: baseline;
      gap: 0.75rem;
      padding: clamp(0.85rem, 2.6vw, 1.15rem) clamp(1rem, 3vw, 1.5rem);
      font-size: calc(var(--font-scale) * clamp(1.05rem, 2.6vw, 1.4rem));
      font-weight: 600;
      color: var(--accent);
      background: rgba(15, 23, 42, 0.02);
    }}
    .team-section summary::-webkit-details-marker {{
      display: none;
    }}
    .team-section summary::after {{
      content: "▾";
      font-size: 0.85em;
      margin-left: auto;
      transition: transform 0.2s ease;
    }}
    .team-section[open] summary::after {{
      transform: rotate(-180deg);
    }}
    .team-name {{
      flex-shrink: 0;
    }}
    .team-meta {{
      font-size: calc(var(--font-scale) * 0.92rem);
      color: #475569;
      font-weight: 500;
    }}
    .team-section-content {{
      padding: clamp(0.95rem, 2.8vw, 1.35rem) clamp(1.05rem, 3vw, 1.6rem) clamp(1.15rem, 3.2vw, 1.65rem);
      border-top: 1px solid var(--border);
      background: #ffffff;
      display: grid;
      gap: clamp(0.85rem, 2.6vw, 1.4rem);
    }}
    .match-group {{
      margin: 0;
      border: 1px solid var(--border);
      border-radius: 0.85rem;
      background: #f8fafc;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
      overflow: hidden;
    }}
    .match-group summary {{
      cursor: pointer;
      padding: clamp(0.8rem, 2.4vw, 1rem) clamp(0.9rem, 2.6vw, 1.2rem);
      font-size: calc(var(--font-scale) * clamp(1rem, 2.4vw, 1.2rem));
      font-weight: 600;
      color: #1e3a8a;
      display: flex;
      align-items: center;
      gap: 0.65rem;
      list-style: none;
    }}
    .match-group summary::-webkit-details-marker {{
      display: none;
    }}
    .match-group summary::after {{
      content: "▾";
      font-size: 0.85em;
      margin-left: auto;
      transition: transform 0.2s ease;
    }}
    .match-group[open] summary::after {{
      transform: rotate(-180deg);
    }}
    .match-content {{
      padding: 0 clamp(0.9rem, 2.6vw, 1.2rem) clamp(1rem, 3vw, 1.4rem);
      border-top: 1px solid var(--border);
      background: #ffffff;
    }}
    .match-list {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: clamp(0.75rem, 2.4vw, 1.1rem);
    }}
    .match-card {{
      background: #f1f5f9;
      border-radius: 0.85rem;
      padding: clamp(0.85rem, 2.6vw, 1.25rem) clamp(0.95rem, 2.8vw, 1.5rem);
      display: grid;
      gap: 0.4rem;
    }}
    .match-header {{
      font-weight: 600;
      color: #1e3a8a;
    }}
    .match-pairing {{
      font-weight: 500;
    }}
    .match-score {{
      font-family: "Fira Mono", "SFMono-Regular", Menlo, Consolas, monospace;
      font-size: calc(var(--font-scale) * 0.9rem);
    }}
    .match-meta {{
      font-size: calc(var(--font-scale) * 0.85rem);
      color: #475569;
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
    }}
    .match-meta a {{
      color: #0f172a;
      font-weight: 600;
      text-decoration: none;
    }}
    .match-meta a:hover,
    .match-meta a:focus-visible {{
      text-decoration: underline;
      outline: none;
    }}
    .group-empty {{
      font-size: calc(var(--font-scale) * 0.9rem);
      color: #64748b;
      margin: 0;
    }}
    .footnote {{
      margin-top: clamp(1.4rem, 3vw, 2.2rem);
      font-size: calc(var(--font-scale) * 0.85rem);
      color: #475569;
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <nav aria-label=\"Navigation\">
        <a href=\"index.html\">⟵ zurück zur Übersicht</a>
      </nav>
      <h1>Internationale Spiele deutscher Frauen-Teams</h1>
    </header>
    <p class=\"meta\">Letzte Aktualisierung: {timestamp}</p>
    <p class=\"footnote\">Alle Angaben stammen aus den offiziellen Ergebnis-Feeds der CEV. Startzeiten werden ohne Zeitzonenangabe veröffentlicht und entsprechen der dort ausgewiesenen Ortszeit.</p>
{competitions_html}
  </main>
</body>
</html>
"""


def main() -> None:
    results: List[tuple[CompetitionConfig, Dict[str, List[MatchRecord]]]] = []
    for comp in COMPETITIONS:
        results.append((comp, collect_matches(comp)))
    html_content = render_html(results)
    OUTPUT_PATH.write_text(html_content + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
