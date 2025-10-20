"""Werkzeuge zum Extrahieren der Startaufstellungen aus Spielberichtsbögen."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pdfplumber
import requests
from bs4 import BeautifulSoup

from .report import (
    BERLIN_TZ,
    DEFAULT_SCHEDULE_URL,
    REQUEST_HEADERS,
    parse_kickoff,
)

SCHEDULE_PAGE_URL = (
    "https://www.volleyball-bundesliga.de/cms/home/"
    "1_bundesliga_frauen/statistik/hauptrunde/spielplan.xhtml?playingScheduleMode=full"
)

PDF_CACHE_DIR = Path("data/lineups")
DEFAULT_OUTPUT_PATH = Path("docs/data/aufstellungen.json")


@dataclass(frozen=True)
class ScheduleRow:
    """Reduziert relevante Felder aus der Spielplan-CSV."""

    match_number: str
    kickoff: datetime
    home_team: str
    away_team: str
    competition: str
    venue: str
    season: str
    result_label: str

    @property
    def is_finished(self) -> bool:
        return bool(self.result_label and self.result_label not in {"-", "–"})


@dataclass(frozen=True)
class SetLineup:
    """Startaufstellung eines Satzes pro Team-Code."""

    number: int
    lineups: Dict[str, List[str]]


@dataclass(frozen=True)
class MatchLineups:
    """Komplette Lineup-Informationen eines Spiels."""

    match: ScheduleRow
    pdf_url: str
    team_names: Dict[str, str]
    sets: List[SetLineup]

    @property
    def usc_code(self) -> Optional[str]:
        for code, name in self.team_names.items():
            if "usc" in _simplify(name):
                return code
        return None

    @property
    def opponent_code(self) -> Optional[str]:
        usc = self.usc_code
        if usc is None:
            return None
        for code in self.team_names:
            if code != usc:
                return code
        return None


def _simplify(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def fetch_schedule_csv(url: str = DEFAULT_SCHEDULE_URL) -> str:
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def parse_schedule(csv_text: str) -> List[ScheduleRow]:
    buffer = csv.DictReader(csv_text.splitlines(), delimiter=";", quotechar='"')
    rows: List[ScheduleRow] = []
    for row in buffer:
        match_number = (row.get("#") or "").strip()
        if not match_number:
            continue
        try:
            kickoff = parse_kickoff(row["Datum"], row["Uhrzeit"])
        except (KeyError, ValueError):
            continue
        home_team = (row.get("Mannschaft 1") or "").strip()
        away_team = (row.get("Mannschaft 2") or "").strip()
        competition = (row.get("Spielrunde") or "").strip()
        venue = (row.get("Austragungsort") or "").strip()
        season = (row.get("Saison") or "").strip()
        result_label = (row.get("Ergebnis") or "").strip()
        rows.append(
            ScheduleRow(
                match_number=match_number,
                kickoff=kickoff,
                home_team=home_team,
                away_team=away_team,
                competition=competition,
                venue=venue,
                season=season,
                result_label=result_label,
            )
        )
    return rows


def find_recent_usc_matches(rows: Sequence[ScheduleRow], limit: int = 2) -> List[ScheduleRow]:
    usc_rows = [
        row
        for row in rows
        if row.is_finished
        and (
            "usc" in _simplify(row.home_team)
            or "usc" in _simplify(row.away_team)
        )
    ]
    usc_rows.sort(key=lambda row: row.kickoff, reverse=True)
    return usc_rows[:limit]


def fetch_schedule_pdf_links(page_url: str = SCHEDULE_PAGE_URL) -> Dict[str, str]:
    response = requests.get(page_url, headers=REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    links: Dict[str, str] = {}
    for anchor in soup.select("a[href]"):
        href = anchor["href"]
        if "scoresheet/pdf" not in href:
            continue
        match = re.search(r"/([0-9]{4})/?$", href)
        if not match:
            continue
        match_number = match.group(1)
        links[match_number] = href
    return links


def download_pdf(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=60)
    response.raise_for_status()
    destination.write_bytes(response.content)
    return destination


def extract_lineups_from_pdf(pdf_path: Path) -> MatchLineups:
    with pdfplumber.open(pdf_path) as pdf:
        tables: List[List[List[str]]] = []
        for page in pdf.pages:
            page_tables = page.extract_tables()
            for table in page_tables:
                if not table:
                    continue
                first_row_text = " ".join(_clean_cell(cell) for cell in table[0])
                if "SATZ" in first_row_text or "S A T Z" in first_row_text:
                    tables.append(table)

        if not tables:
            raise ValueError(f"Keine Satz-Tabellen in {pdf_path} gefunden.")

        team_codes = _extract_team_codes(pdf.pages[0])

        set_lineups: List[SetLineup] = []
        for table in tables:
            set_number = _detect_set_number(table)
            if set_number is None:
                continue
            lineups = _extract_positions_from_table(table)
            if not lineups:
                continue
            set_lineups.append(SetLineup(number=set_number, lineups=lineups))

    set_lineups.sort(key=lambda item: item.number)

    # Platzhalter – eigentliche Match-Infos werden später ergänzt.
    dummy_match = ScheduleRow(
        match_number="0",
        kickoff=datetime.now(tz=BERLIN_TZ),
        home_team=team_codes.get("B", ""),
        away_team=team_codes.get("A", ""),
        competition="",
        venue="",
        season="",
        result_label="",
    )
    return MatchLineups(
        match=dummy_match,
        pdf_url="",
        team_names=team_codes,
        sets=set_lineups,
    )


def _clean_cell(cell: Optional[str]) -> str:
    if cell is None:
        return ""
    text = str(cell).replace("\xa0", " ")
    text = text.replace("\n", " ")
    return " ".join(text.split())


def _extract_team_codes(page: pdfplumber.page.Page) -> Dict[str, str]:
    words = page.extract_words()
    joined = " ".join(word["text"] for word in words[:200])
    match = re.search(r"\b([AB])\s+(.+?)\s+vs\.\s+(.+?)\s+([AB])\b", joined)
    if not match:
        raise ValueError("Team-Codes konnten nicht ermittelt werden.")
    left_code, left_name, right_name, right_code = match.groups()
    return {
        left_code: left_name.strip(),
        right_code: right_name.strip(),
    }


def _detect_set_number(table: Sequence[Sequence[str]]) -> Optional[int]:
    first_row_text = " ".join(_clean_cell(cell) for cell in table[0])
    normalized = first_row_text.replace(" ", "")
    match = re.search(r"SATZ(\d)", normalized)
    if match:
        return int(match.group(1))
    match = re.search(r"SATS(\d)", normalized)
    if match:
        return int(match.group(1))
    return None


def _extract_positions_from_table(
    table: Sequence[Sequence[str]],
) -> Dict[str, List[str]]:
    rows = [[_clean_cell(cell) for cell in row] for row in table]
    header_info = _find_header_indices(rows)
    if header_info:
        header_index, left_cols, right_cols, team_codes = header_info
        for row in rows[header_index + 1 :]:
            left_values = _collect_positions(row, left_cols)
            right_values = _collect_positions(row, right_cols)
            if len(left_values) == 6 and len(right_values) == 6:
                return {
                    team_codes[0]: left_values,
                    team_codes[1]: right_values,
                }

    # Fallback für Tabellen ohne klaren Header (z. B. Satz 5)
    team_order = _detect_codes_from_row(rows[0])
    fallback_row_index = 1 if len(rows) > 1 else 0
    fallback_row = rows[fallback_row_index]
    skip_cols = {
        index
        for index, value in enumerate(rows[0])
        if any(keyword in value for keyword in {"Punkte", "Wechsel", "Auszeit"})
    }
    digit_cols = [
        index
        for index, value in enumerate(fallback_row)
        if index not in skip_cols and re.search(r"\b\d{1,2}\b", value)
    ]
    if len(digit_cols) >= 12:
        left_cols = digit_cols[:6]
        right_cols = digit_cols[6:12]
        left = _collect_positions(fallback_row, left_cols)
        right = _collect_positions(fallback_row, right_cols)
        if len(left) == 6 and len(right) == 6:
            if team_order:
                return {team_order[0]: left, team_order[1]: right}
            return {"left": left, "right": right}

    return {}


def _find_header_indices(
    rows: Sequence[Sequence[str]],
) -> Optional[Tuple[int, List[int], List[int], Tuple[str, str]]]:
    for index, row in enumerate(rows):
        roman_cols = [i for i, value in enumerate(row) if value in {"I", "II", "III", "IV", "V", "VI"}]
        if len(roman_cols) >= 12:
            team_codes = _detect_codes_from_row(row)
            if team_codes is None and index > 0:
                team_codes = _detect_codes_from_row(rows[index - 1])
            if team_codes is None:
                continue
            left_cols = roman_cols[:6]
            right_cols = roman_cols[6:12]
            return index, left_cols, right_cols, team_codes
    return None


def _detect_codes_from_row(row: Sequence[str]) -> Optional[Tuple[str, str]]:
    text = " ".join(row)
    codes: List[str] = []
    for match in re.finditer(r"\b([AB])\s+[A-Za-zÄÖÜäöüß]{2,}", text):
        code = match.group(1)
        if code not in codes:
            codes.append(code)
        if len(codes) == 2:
            return codes[0], codes[1]
    return None


def _collect_positions(row: Sequence[str], columns: Sequence[int]) -> List[str]:
    values: List[str] = []
    for col in columns:
        if col >= len(row):
            continue
        value = row[col]
        match = re.search(r"\b\d{1,2}\b", value)
        if match:
            values.append(match.group(0))
    return values[:6]


def merge_schedule_details(
    schedule_row: ScheduleRow,
    pdf_url: str,
    pdf_lineups: MatchLineups,
) -> MatchLineups:
    return MatchLineups(
        match=schedule_row,
        pdf_url=pdf_url,
        team_names=pdf_lineups.team_names,
        sets=pdf_lineups.sets,
    )


def build_lineup_dataset(
    *,
    limit: int = 2,
    schedule_csv_url: str = DEFAULT_SCHEDULE_URL,
    schedule_page_url: str = SCHEDULE_PAGE_URL,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> Dict[str, object]:
    csv_text = fetch_schedule_csv(schedule_csv_url)
    schedule_rows = parse_schedule(csv_text)
    recent_rows = find_recent_usc_matches(schedule_rows, limit=limit)
    if not recent_rows:
        raise RuntimeError("Keine abgeschlossenen USC-Spiele gefunden.")

    pdf_links = fetch_schedule_pdf_links(schedule_page_url)

    matches: List[MatchLineups] = []
    for row in recent_rows:
        pdf_url = pdf_links.get(row.match_number)
        if not pdf_url:
            raise RuntimeError(f"Kein PDF-Link für Spiel {row.match_number} gefunden.")
        pdf_path = PDF_CACHE_DIR / f"{row.match_number}.pdf"
        download_pdf(pdf_url, pdf_path)
        pdf_lineups = extract_lineups_from_pdf(pdf_path)
        matches.append(merge_schedule_details(row, pdf_url, pdf_lineups))

    dataset = _serialize_dataset(matches)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    return dataset


def _serialize_dataset(matches: Sequence[MatchLineups]) -> Dict[str, object]:
    serialized: List[Dict[str, object]] = []
    for match in matches:
        usc_code = match.usc_code
        opponent_code = match.opponent_code
        serialized_sets: List[Dict[str, object]] = []
        for set_lineup in match.sets:
            lineups: Dict[str, List[str]] = {}
            for code, positions in set_lineup.lineups.items():
                lineups[code] = positions
            if usc_code in lineups and opponent_code in lineups:
                serialized_sets.append(
                    {
                        "number": set_lineup.number,
                        "lineups": {
                            "usc": lineups[usc_code],
                            "opponent": lineups[opponent_code],
                        },
                    }
                )
            else:
                serialized_sets.append(
                    {
                        "number": set_lineup.number,
                        "lineups": {
                            code: positions for code, positions in lineups.items()
                        },
                    }
                )

        serialized.append(
            {
                "match_number": match.match.match_number,
                "kickoff": match.match.kickoff.isoformat(),
                "date_label": match.match.kickoff.strftime("%d.%m.%Y"),
                "home_team": match.match.home_team,
                "away_team": match.match.away_team,
                "competition": match.match.competition,
                "venue": match.match.venue,
                "season": match.match.season,
                "result": match.match.result_label,
                "pdf_url": match.pdf_url,
                "team_codes": match.team_names,
                "usc_code": usc_code,
                "opponent_code": opponent_code,
                "sets": serialized_sets,
            }
        )

    return {
        "generated_at": datetime.now(tz=BERLIN_TZ).isoformat(),
        "matches": serialized,
    }


def main() -> int:
    dataset = build_lineup_dataset()
    print(
        f"Lineup-Datensatz mit {len(dataset['matches'])} Begegnungen "
        f"in {DEFAULT_OUTPUT_PATH} gespeichert."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

