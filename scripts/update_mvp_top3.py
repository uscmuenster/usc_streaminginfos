from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Sequence
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LINEUPS_PATH = REPO_ROOT / "docs" / "data" / "aufstellungen.json"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "docs" / "data" / "mvp_top3.json"

URL = "https://www.volleyball-bundesliga.de/cms/home/1_bundesliga_frauen/statistik/mvp_rankings/spielerinnenranking_hauptrunde.xhtml"

FORM = "samsCmsComponentSubViewForComponent30088103:componentForm_30088103"
SELECTOR = f"{FORM}:indicatorSelector_30088103"
SELECTOR_INPUT = f"{SELECTOR}_input"
TABLE = f"{FORM}:rankingTable"

HEADERS = {"User-Agent": "Mozilla/5.0"}


class MVPDatasetError(RuntimeError):
    pass


def _load_team_information(lineups_path: Path) -> tuple[str, str]:
    try:
        with lineups_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError as exc:
        raise MVPDatasetError(f"Lineup dataset not found at '{lineups_path}'.") from exc
    except json.JSONDecodeError as exc:
        raise MVPDatasetError(f"Lineup dataset at '{lineups_path}' is not valid JSON.") from exc

    home_team = str(payload.get("home_team") or payload.get("usc_team") or "USC Münster")
    opponent_team = payload.get("opponent_team")

    if not opponent_team:
        raise MVPDatasetError("Could not determine opponent team from lineup dataset.")

    return home_team, str(opponent_team)


def get_viewstate(session: requests.Session) -> tuple[str, BeautifulSoup]:
    response = session.get(URL, headers=HEADERS)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    viewstate = soup.select_one("input[name='jakarta.faces.ViewState']")
    if not viewstate or "value" not in viewstate.attrs:
        raise MVPDatasetError("Could not read jakarta.faces.ViewState from MVP page.")

    return str(viewstate["value"]), soup


def extract_indicators(soup: BeautifulSoup) -> Dict[str, str]:
    indicators: Dict[str, str] = {}

    for option in soup.select("select[id$='indicatorSelector_30088103_input'] option"):
        value = option.get("value", "").strip()
        if value:
            indicators[value] = option.get_text(strip=True)

    if not indicators:
        raise MVPDatasetError("No MVP indicators found on source page.")

    return indicators


def parse_partial(xml_payload: str) -> tuple[str, str | None]:
    root = ElementTree.fromstring(xml_payload)

    html = ""
    viewstate = ""

    for update in root.findall(".//update"):
        update_id = update.get("id")

        if update_id in {TABLE, f"{FORM}:rankingPanel"}:
            html = update.text or ""

        if update_id == "jakarta.faces.ViewState":
            viewstate = update.text or ""

    if not html:
        raise MVPDatasetError("MVP partial response did not contain a ranking table.")

    return html, (viewstate or None)


def parse_table(html: str, *, headers: Sequence[str] | None = None) -> tuple[List[Dict[str, str]], List[str]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table")

    resolved_headers = list(headers or [])

    if table is not None and not resolved_headers:
        for th in table.select("thead th"):
            label = th.get_text(" ", strip=True)
            resolved_headers.append(label if label else f"col_{len(resolved_headers)}")

    rows: List[Dict[str, str]] = []

    row_selector = "tbody tr" if table is not None else "tr"

    for tr in (table.select(row_selector) if table is not None else soup.select(row_selector)):
        cells = [cell.get_text(" ", strip=True) for cell in tr.select("td")]

        if not cells:
            continue

        row: Dict[str, str] = {}

        for i, value in enumerate(cells):
            key = resolved_headers[i] if i < len(resolved_headers) else f"col_{i}"
            row[key] = value

        rows.append(row)

    return rows, resolved_headers


def get_pages(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    paginator = soup.select_one(".ui-paginator-current")

    if not paginator:
        return 1

    match = re.search(r"Seite\s+\d+\/(\d+)", paginator.get_text(" ", strip=True))

    return int(match.group(1)) if match else 1


def fetch_page(session: requests.Session, page: int, viewstate: str) -> tuple[str, str]:
    first = page * 25

    payload = {
        "jakarta.faces.partial.ajax": "true",
        "jakarta.faces.source": TABLE,
        "jakarta.faces.partial.execute": TABLE,
        "jakarta.faces.partial.render": f"{FORM}:rankingPanel",
        FORM: FORM,
        f"{TABLE}_pagination": "true",
        f"{TABLE}_first": str(first),
        f"{TABLE}_rows": "25",
        f"{TABLE}_encodeFeature": "true",
        f"{TABLE}_page": str(page),
        "jakarta.faces.ViewState": viewstate,
    }

    response = session.post(URL, data=payload, headers=HEADERS)
    response.raise_for_status()

    html, next_viewstate = parse_partial(response.text)
    return html, (next_viewstate or viewstate)


def fetch_indicator(
    session: requests.Session,
    indicator: str,
    viewstate: str,
    *,
    max_rows: int = 100,
) -> tuple[List[Dict[str, str]], int, str]:
    payload = {
        "jakarta.faces.partial.ajax": "true",
        "jakarta.faces.source": SELECTOR,
        "jakarta.faces.partial.execute": SELECTOR,
        "jakarta.faces.partial.render": f"{FORM}:rankingPanel",
        "jakarta.faces.behavior.event": "change",
        "jakarta.faces.partial.event": "change",
        FORM: FORM,
        SELECTOR_INPUT: indicator,
        "jakarta.faces.ViewState": viewstate,
    }

    response = session.post(URL, data=payload, headers=HEADERS)
    response.raise_for_status()

    html, next_viewstate = parse_partial(response.text)
    current_viewstate = next_viewstate or viewstate
    rows, headers = parse_table(html)
    pages = get_pages(html)

    if max_rows > 25 and pages > 1:
        max_pages = min(pages, (max_rows + 24) // 25)

        for page in range(1, max_pages):
            page_html, current_viewstate = fetch_page(session, page, current_viewstate)
            page_rows, _ = parse_table(page_html, headers=headers)
            rows.extend(page_rows)

            if len(rows) >= max_rows:
                rows = rows[:max_rows]
                break

    return rows, pages, current_viewstate


def top_players(rows: List[Dict[str, str]], team: str, limit: int = 3) -> List[Dict[str, str]]:
    cleaned = team.replace("-", " ").strip()
    team_terms = [part.lower() for part in cleaned.split() if part]
    search_terms = {cleaned.lower(), team.lower()}

    if team_terms:
        search_terms.add(team_terms[-1])

    filtered: List[Dict[str, str]] = []

    for row in rows:
        team_value = row.get("Mannschaft", "")
        team_value_lower = team_value.lower()

        if any(term and term in team_value_lower for term in search_terms):
            filtered.append(row)

    return filtered[:limit]


def build_dataset(home_team: str, opponent_team: str, *, limit: int = 3, scan_limit: int = 50) -> Mapping[str, object]:
    session = requests.Session()

    viewstate, soup = get_viewstate(session)
    indicators = extract_indicators(soup)
    effective_scan_limit = min(scan_limit, 50)

    result = []

    for indicator_id, label in indicators.items():
        rows, pages, viewstate = fetch_indicator(
            session,
            indicator_id,
            viewstate,
            max_rows=effective_scan_limit,
        )

        result.append(
            {
                "id": indicator_id,
                "label": label,
                "pages": pages,
                "all_players": rows,
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "home_team": home_team,
        "usc_team": home_team,
        "opponent_team": opponent_team,
        "limit": limit,
        "scan_limit": effective_scan_limit,
        "indicators": result,
    }


def dump_dataset(dataset: Mapping[str, object], *, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(dataset, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate MVP Top 3 dataset for home team and opponent.")

    parser.add_argument("--usc-team", dest="home_team")
    parser.add_argument("--home-team", dest="home_team")
    parser.add_argument("--opponent-team")
    parser.add_argument("--lineups-path", type=Path, default=DEFAULT_LINEUPS_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--scan-limit", type=int, default=50)

    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)

    home_team = args.home_team
    opponent_team = args.opponent_team

    if not home_team or not opponent_team:
        home_team_ds, opponent_team_ds = _load_team_information(args.lineups_path)
        home_team = home_team or home_team_ds
        opponent_team = opponent_team or opponent_team_ds

    dataset = build_dataset(home_team, opponent_team, limit=args.limit, scan_limit=args.scan_limit)
    dump_dataset(dataset, output_path=args.output)


if __name__ == "__main__":
    main()
