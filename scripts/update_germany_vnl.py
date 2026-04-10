#!/usr/bin/env python3
"""Generate docs/germany_vnl.html with a daily refreshed Germany VNL overview."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.request import Request, urlopen

OUTPUT_PATH = Path("docs/germany_vnl.html")
LINK_DATA_PATH = Path("docs/data/germany_vnl_links.json")
REQUEST_TIMEOUT_SECONDS = 12
USER_AGENT = "usc-streaminginfos-bot/1.0 (+https://github.com/)"


@dataclass(frozen=True)
class VnlMatch:
    match_date: date
    opponent: str
    competition: str
    match_url: str
    slug: str


@dataclass(frozen=True)
class SourceLink:
    key: str
    label: str
    url: str


@dataclass(frozen=True)
class SourceLinkInfo:
    key: str
    label: str
    url: str
    page_title: str
    page_description: str
    fetched_at_utc: str


# Hinweis: Falls neue offizielle Match-Links vorliegen, hier ergänzen.
MATCHES: tuple[VnlMatch, ...] = (
    VnlMatch(
        match_date=date(2026, 6, 4),
        opponent="Kanada",
        competition="VNL Frauen 2026",
        match_url=(
            "https://en.volleyballworld.com/volleyball/competitions/"
            "volleyball-nations-league/schedule/26558/?match=canada-vs-germany"
        ),
        slug="canada-vs-germany",
    ),
)


SOURCE_LINKS: tuple[SourceLink, ...] = (
    SourceLink(
        key="germany_schedule_1",
        label="Germany Team Schedule (Start: dynamisch)",
        url=(
            "https://en.volleyballworld.com/volleyball/competitions/"
            "volleyball-nations-league/teams/women/8625/schedule/"
        ),
    ),
    SourceLink(
        key="head_to_head",
        label="Head-to-Head",
        url=(
            "https://en.volleyballworld.com/volleyball/competitions/"
            "volleyball-nations-league/schedule/26558/#head-to-head"
        ),
    ),
    SourceLink(
        key="germany_squad",
        label="Germany Kader",
        url=(
            "https://en.volleyballworld.com/volleyball/competitions/"
            "volleyball-nations-league/teams/women/8625/players/?"
        ),
    ),
    SourceLink(
        key="standings",
        label="VNL Standings (Frauen)",
        url=(
            "https://en.volleyballworld.com/volleyball/competitions/"
            "volleyball-nations-league/standings/women/#advanced"
        ),
    ),
    SourceLink(
        key="world_ranking",
        label="Weltrangliste (Frauen)",
        url="https://en.volleyballworld.com/volleyball/world-ranking/women?",
    ),
)


def pick_next_match(today: date) -> VnlMatch:
    for match in sorted(MATCHES, key=lambda item: item.match_date):
        if match.match_date >= today:
            return match
    return sorted(MATCHES, key=lambda item: item.match_date)[-1]


def strip_tags(value: str) -> str:
    cleaned = re.sub(r"<script[\\s\\S]*?</script>", "", value, flags=re.IGNORECASE)
    cleaned = re.sub(r"<style[\\s\\S]*?</style>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\\s+", " ", unescape(cleaned)).strip()
    return cleaned


def extract_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return "Titel nicht verfügbar"
    return strip_tags(match.group(1)) or "Titel nicht verfügbar"


def extract_description(html: str) -> str:
    meta_match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if meta_match:
        text = strip_tags(meta_match.group(1))
        if text:
            return text

    first_heading = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.IGNORECASE | re.DOTALL)
    if first_heading:
        heading = strip_tags(first_heading.group(1))
        if heading:
            return heading

    return "Beschreibung nicht verfügbar"


def fetch_link_info(link: SourceLink, fetched_at: datetime) -> SourceLinkInfo:
    request = Request(link.url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            html = response.read().decode(charset, errors="replace")
            title = extract_title(html)
            description = extract_description(html)
    except URLError:
        title = "Abruf fehlgeschlagen"
        description = "Die Quelle konnte beim Build nicht geladen werden."

    return SourceLinkInfo(
        key=link.key,
        label=link.label,
        url=link.url,
        page_title=title,
        page_description=description,
        fetched_at_utc=fetched_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def collect_source_infos(source_links: Iterable[SourceLink], fetched_at: datetime) -> list[SourceLinkInfo]:
    return [fetch_link_info(link, fetched_at) for link in source_links]


def render_source_info_cards(source_infos: Iterable[SourceLinkInfo]) -> str:
    cards: list[str] = []
    for source in source_infos:
        cards.append(
            "\n".join(
                [
                    '        <article class="tile source-tile">',
                    f"          <strong>{source.label}</strong>",
                    f"          <span class=\"source-title\">{source.page_title}</span>",
                    f"          <span class=\"source-description\">{source.page_description}</span>",
                    (
                        f"          <a href=\"{source.url}\" target=\"_blank\" rel=\"noopener\">"
                        "Quelle öffnen</a>"
                    ),
                    "        </article>",
                ]
            )
        )
    return "\n".join(cards)


def render_html(
    next_match: VnlMatch,
    source_infos: list[SourceLinkInfo],
    today: date,
    built_at: datetime,
) -> str:
    pretty_match_date = next_match.match_date.strftime("%d.%m.%Y")
    updated_iso = built_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    updated_pretty = today.strftime("%d.%m.%Y")
    source_cards = render_source_info_cards(source_infos)

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Germany VNL – Nächster Gegner</title>
  <style>
    :root {{
      --black: #111111;
      --red: #d00000;
      --gold: #ffce00;
      --paper: #fff8de;
      --muted: #f3e9b4;
      --text: #151515;
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      font-family: Inter, "Segoe UI", Roboto, Arial, sans-serif;
      background: linear-gradient(180deg, var(--black) 0 30%, #2a0000 30% 65%, #4a3900 65% 100%);
      color: var(--text);
      min-height: 100vh;
      padding: 24px;
    }}

    main {{
      max-width: 980px;
      margin: 0 auto;
      background: var(--paper);
      border: 3px solid var(--gold);
      border-radius: 16px;
      box-shadow: 0 14px 40px rgba(0, 0, 0, 0.35);
      padding: 24px;
    }}

    .flag-strip {{
      height: 10px;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--black) 0 33.33%, var(--red) 33.33% 66.66%, var(--gold) 66.66% 100%);
      margin-bottom: 18px;
    }}

    h1 {{
      margin: 0 0 8px;
      color: var(--black);
      font-size: clamp(1.4rem, 2.2vw, 2rem);
    }}

    .subtitle {{
      margin: 0 0 18px;
      color: #4d4d4d;
    }}

    .next-opponent {{
      background: #fff;
      border: 2px solid var(--red);
      border-radius: 14px;
      padding: 18px;
      margin-bottom: 20px;
    }}

    .next-opponent h2 {{
      margin: 0 0 14px;
      color: var(--red);
    }}

    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }}

    .tile {{
      background: var(--muted);
      border-radius: 10px;
      border-left: 6px solid var(--gold);
      padding: 12px;
    }}

    .tile strong {{ display: block; margin-bottom: 4px; }}

    .links {{
      background: #ffffff;
      border-radius: 12px;
      border: 1px solid #ddd;
      padding: 14px 18px;
    }}

    .links h3 {{ margin-top: 0; }}

    .source-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }}

    .source-tile a {{
      display: inline-block;
      margin-top: 8px;
    }}

    .source-title {{
      display: block;
      font-weight: 600;
      margin-bottom: 4px;
    }}

    .source-description {{
      display: block;
      color: #2e2e2e;
      font-size: 0.95rem;
      line-height: 1.35;
    }}

    .updated {{
      margin-top: 18px;
      color: #555;
      font-size: 0.92rem;
    }}

    a {{ color: #9a0000; }}
  </style>
</head>
<body>
  <main>
    <div class="flag-strip" aria-hidden="true"></div>
    <h1>Volleyball Nations League – Germany (Frauen)</h1>
    <p class="subtitle">Nächster Gegner der deutschen Nationalmannschaft.</p>

    <section class="next-opponent" aria-labelledby="next-opponent-title">
      <h2 id="next-opponent-title">Nächster Gegner</h2>
      <div class="grid">
        <article class="tile">
          <strong>Gegner</strong>
          <span id="opponent-name">{next_match.opponent}</span>
        </article>
        <article class="tile">
          <strong>Datum</strong>
          <span>{pretty_match_date}</span>
        </article>
        <article class="tile">
          <strong>Wettbewerb</strong>
          <span>{next_match.competition}</span>
        </article>
        <article class="tile">
          <strong>Match-Link</strong>
          <a id="match-link" href="{next_match.match_url}" target="_blank" rel="noopener">{next_match.slug}</a>
        </article>
      </div>
    </section>

    <section class="links" aria-labelledby="source-links-title">
      <h3 id="source-links-title">Ausgelesene VNL-Quellen</h3>
      <div class="source-grid">
{source_cards}
      </div>
    </section>

    <p class="updated">Zuletzt aktualisiert: {updated_pretty} (UTC-Build: {updated_iso})</p>
  </main>
</body>
</html>
"""


def write_link_data(source_infos: list[SourceLinkInfo]) -> None:
    LINK_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    serializable = [asdict(source) for source in source_infos]
    LINK_DATA_PATH.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    built_at = datetime.now(timezone.utc)
    today = built_at.date()
    next_match = pick_next_match(today)
    source_infos = collect_source_infos(SOURCE_LINKS, built_at)
    write_link_data(source_infos)
    OUTPUT_PATH.write_text(
        render_html(next_match, source_infos, today, built_at),
        encoding="utf-8",
    )
    print(f"Updated {OUTPUT_PATH} and {LINK_DATA_PATH} for {today.isoformat()}")


if __name__ == "__main__":
    main()
