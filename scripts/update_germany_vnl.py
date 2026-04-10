#!/usr/bin/env python3
"""Generate docs/germany_vnl.html with a daily refreshed Germany VNL overview."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

OUTPUT_PATH = Path("docs/germany_vnl.html")


@dataclass(frozen=True)
class VnlMatch:
    match_date: date
    opponent: str
    competition: str
    match_url: str
    slug: str


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


def pick_next_match(today: date) -> VnlMatch:
    for match in sorted(MATCHES, key=lambda item: item.match_date):
        if match.match_date >= today:
            return match
    return sorted(MATCHES, key=lambda item: item.match_date)[-1]


def render_html(next_match: VnlMatch, today: date, built_at: datetime) -> str:
    from_date_1 = next_match.match_date.strftime("%Y-%m-%d")
    from_date_2 = (next_match.match_date + timedelta(days=7)).strftime("%Y-%m-%d")
    pretty_match_date = next_match.match_date.strftime("%d.%m.%Y")
    updated_iso = built_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    updated_pretty = today.strftime("%d.%m.%Y")

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

    .links ul {{ margin: 0; padding-left: 18px; }}

    .links li {{ margin: 8px 0; }}

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
    <p class="subtitle">Nächster Gegner der deutschen Nationalmannschaft in einer schwarz-rot-goldenen Ansicht.</p>

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
      <h3 id="source-links-title">Nützliche VNL-Links</h3>
      <ul>
        <li><a href="https://en.volleyballworld.com/volleyball/competitions/volleyball-nations-league/teams/women/8625/schedule/#fromDate={from_date_1}" target="_blank" rel="noopener">Germany Team Schedule (Start: {from_date_1})</a></li>
        <li><a href="https://en.volleyballworld.com/volleyball/competitions/volleyball-nations-league/teams/women/8625/schedule/#fromDate={from_date_2}" target="_blank" rel="noopener">Germany Team Schedule (Start: {from_date_2})</a></li>
        <li><a href="https://en.volleyballworld.com/volleyball/competitions/volleyball-nations-league/schedule/26558/#head-to-head" target="_blank" rel="noopener">Head-to-Head</a></li>
        <li><a href="https://en.volleyballworld.com/volleyball/competitions/volleyball-nations-league/teams/women/8625/players/?" target="_blank" rel="noopener">Germany Kader</a></li>
        <li><a href="https://en.volleyballworld.com/volleyball/competitions/volleyball-nations-league/standings/women/#advanced" target="_blank" rel="noopener">VNL Standings (Frauen)</a></li>
        <li><a href="https://en.volleyballworld.com/volleyball/world-ranking/women?" target="_blank" rel="noopener">Weltrangliste (Frauen)</a></li>
      </ul>
    </section>

    <p class="updated">Zuletzt aktualisiert: {updated_pretty} (UTC-Build: {updated_iso})</p>
  </main>
</body>
</html>
"""


def main() -> None:
    built_at = datetime.now(timezone.utc)
    today = built_at.date()
    next_match = pick_next_match(today)
    OUTPUT_PATH.write_text(render_html(next_match, today, built_at), encoding="utf-8")
    print(f"Updated {OUTPUT_PATH} for {today.isoformat()} -> {next_match.opponent}")


if __name__ == "__main__":
    main()
