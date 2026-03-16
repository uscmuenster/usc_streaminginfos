"""Werkzeuge zum Extrahieren der Startaufstellungen aus Spielberichtsbögen."""

from __future__ import annotations

import csv
import difflib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pdfplumber
import requests
from bs4 import BeautifulSoup

from .report import (
    BERLIN_TZ,
    DEFAULT_SCHEDULE_ICS_URL,
    DEFAULT_SCHEDULE_URL,
    VBL_PLAYOFFS_SCHEDULE_URL,
    REQUEST_HEADERS,
    USC_CANONICAL_NAME,
    fetch_ics_schedule,
    collect_team_roster,
    parse_ics_schedule,
    _decode_csv_bytes_robust,
    _normalize_schedule_field,
    extract_schedule_result_label,
    parse_schedule_kickoff,
)

SCHEDULE_PAGE_URL = (
    "https://www.volleyball-bundesliga.de/cms/home/"
    "1_bundesliga_frauen/statistik/hauptrunde/spielplan.xhtml?playingScheduleMode=full"
)

PDF_CACHE_DIR = Path("data/lineups")
DEFAULT_OUTPUT_PATH = Path("docs/data/aufstellungen.json")
ROSTER_CACHE_DIR = Path("data/rosters")

POSITION_SLOTS = ["I", "II", "III", "IV", "V", "VI"]

# Zusätzlicher iCal-Feed für Playoffs (matchSeriesId=776311124)
VBL_PLAYOFFS_SCHEDULE_ICS_URL = (
    "https://www.volleyball-bundesliga.de/iCal/matchSeries/"
    "matches.ical?matchSeriesId=776311124&calenderType=ics"
)

DEFAULT_ADDITIONAL_SCHEDULE_URLS: Tuple[str, ...] = (
    VBL_PLAYOFFS_SCHEDULE_URL,
)

DEFAULT_ADDITIONAL_SCHEDULE_ICS_URLS: Tuple[str, ...] = (
    VBL_PLAYOFFS_SCHEDULE_ICS_URL,
)


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
    score: Optional[str]
    total_points: Optional[str]
    set_scores: Tuple[str, ...]

    @property
    def is_finished(self) -> bool:
        return bool(self.result_label and self.result_label not in {"-", "–"})


@dataclass(frozen=True)
class SetLineup:
    """Startaufstellung eines Satzes pro Team-Code."""

    number: int
    lineups: Dict[str, List[str]]
    scores: Dict[str, Optional[str]]


@dataclass(frozen=True)
class MatchLineups:
    """Komplette Lineup-Informationen eines Spiels."""

    match: ScheduleRow
    pdf_url: str
    team_names: Dict[str, str]
    sets: List[SetLineup]
    rosters: Dict[str, Dict[str, str]]

    @property
    def usc_code(self) -> Optional[str]:
        """Backward-compatible alias – only works when the home team is USC Münster."""
        for code, name in self.team_names.items():
            if "usc" in _simplify(name):
                return code
        return None

    @property
    def opponent_code(self) -> Optional[str]:
        """Backward-compatible alias – returns the non-USC team code."""
        usc = self.usc_code
        if usc is None:
            return None
        for code in self.team_names:
            if code != usc:
                return code
        return None

    def get_home_code(self, home_team: str) -> Optional[str]:
        """Return the PDF team code for the configured *home_team* (Unicode-aware)."""
        return _find_team_code(self.team_names, home_team)

    def get_opponent_code(self, home_team: str) -> Optional[str]:
        """Return the PDF team code for the opponent of *home_team*."""
        home = self.get_home_code(home_team)
        if home is None:
            return None
        for code in self.team_names:
            if code != home:
                return code
        return None


def _simplify(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _normalize_team_name(value: str) -> str:
    """Normalize a team name for Unicode-aware comparison (handles umlaut variants)."""
    nfkd = unicodedata.normalize("NFKD", value)
    stripped = "".join(char for char in nfkd if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", stripped).strip().casefold()


def _find_team_code(team_names: Dict[str, str], target_name: str) -> Optional[str]:
    """Find the PDF team code that matches *target_name*.

    Tries three strategies in order:
    1. Exact case-folded match (fast path).
    2. Unicode-normalized match – handles umlaut variants (e.g. ``Münster`` ↔ ``Munster``).
    3. Substring match – handles abbreviated PDF names (e.g. ``USC`` in ``USC Münster``).
    """
    # 1. Exact case-insensitive + whitespace-normalized match
    simplified_target = _simplify(target_name)
    for code, name in team_names.items():
        if _simplify(name) == simplified_target:
            return code
    # 2. Unicode-normalized match (strips combining chars, e.g. ü → u)
    unicode_target = _normalize_team_name(target_name)
    for code, name in team_names.items():
        if _normalize_team_name(name) == unicode_target:
            return code
    # 3. Substring match (PDF may use abbreviated/truncated team names)
    for code, name in team_names.items():
        norm_name = _normalize_team_name(name)
        if unicode_target in norm_name or norm_name in unicode_target:
            return code
    return None


def fetch_schedule_csv(url: str = DEFAULT_SCHEDULE_URL) -> str:
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    return _decode_csv_bytes_robust(response.content)


def parse_schedule(csv_text: str) -> List[ScheduleRow]:
    buffer = csv.DictReader(csv_text.splitlines(), delimiter=";", quotechar='"')
    rows: List[ScheduleRow] = []
    for row in buffer:
        match_number = _normalize_schedule_field(row.get("#")) or ""
        if not match_number:
            continue
        try:
            kickoff = parse_schedule_kickoff(row)
        except (KeyError, ValueError):
            continue
        home_team = _normalize_schedule_field(row.get("Mannschaft 1")) or ""
        away_team = _normalize_schedule_field(row.get("Mannschaft 2")) or ""
        competition = _normalize_schedule_field(row.get("Spielrunde")) or ""
        venue = _normalize_schedule_field(row.get("Austragungsort")) or ""
        season = _normalize_schedule_field(row.get("Saison")) or ""
        result_label = extract_schedule_result_label(row)

        score = _normalize_schedule_field(row.get("Satzpunkte"))
        total_points = _normalize_schedule_field(row.get("Ballpunkte"))
        set_scores: List[str] = []
        for index in range(1, 6):
            home_key = f"Satz {index} - Ballpunkte 1"
            away_key = f"Satz {index} - Ballpunkte 2"
            home_points = _normalize_schedule_field(row.get(home_key)) or ""
            away_points = _normalize_schedule_field(row.get(away_key)) or ""
            if home_points and away_points:
                set_scores.append(f"{home_points}:{away_points}")
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
                score=score,
                total_points=total_points,
                set_scores=tuple(set_scores),
            )
        )
    return rows


def find_recent_matches_for_home_team(
    rows: Sequence[ScheduleRow],
    home_team: str,
    limit: int = 2,
) -> List[ScheduleRow]:
    """Gibt die letzten *limit* abgeschlossenen Spiele des Heimteams zurück."""
    target = _simplify(home_team)
    team_rows = [
        row
        for row in rows
        if row.is_finished
        and (
            target in _simplify(row.home_team)
            or target in _simplify(row.away_team)
        )
    ]
    team_rows.sort(key=lambda row: row.kickoff, reverse=True)
    return team_rows[:limit]


def find_recent_usc_matches(rows: Sequence[ScheduleRow], limit: int = 2) -> List[ScheduleRow]:
    """Rückwärtskompatible Variante von find_recent_matches_for_home_team."""
    return find_recent_matches_for_home_team(rows, USC_CANONICAL_NAME, limit=limit)


def find_next_home_match_row(
    rows: Sequence[ScheduleRow],
    home_team: str,
    *,
    reference: Optional[datetime] = None,
) -> Optional[ScheduleRow]:
    """Gibt das nächste Heimspiel von *home_team* zurück."""
    now = reference or datetime.now(tz=BERLIN_TZ)
    target = _simplify(home_team)
    home_games = [
        row
        for row in rows
        if row.kickoff >= now and target in _simplify(row.home_team)
    ]
    home_games.sort(key=lambda row: row.kickoff)
    return home_games[0] if home_games else None


def find_next_usc_home_match_row(
    rows: Sequence[ScheduleRow],
    *,
    reference: Optional[datetime] = None,
) -> Optional[ScheduleRow]:
    """Rückwärtskompatible Variante von find_next_home_match_row."""
    return find_next_home_match_row(rows, USC_CANONICAL_NAME, reference=reference)


def find_next_home_match_from_ics(
    *,
    home_team: str,
    schedule_ics_url: str = DEFAULT_SCHEDULE_ICS_URL,
    additional_schedule_ics_urls: Sequence[str] = DEFAULT_ADDITIONAL_SCHEDULE_ICS_URLS,
    reference: Optional[datetime] = None,
) -> Optional[ScheduleRow]:
    now = reference or datetime.now(tz=BERLIN_TZ)
    target = _simplify(home_team)
    urls: List[str] = [schedule_ics_url]
    for url in additional_schedule_ics_urls:
        if url and url not in urls:
            urls.append(url)

    candidates: List[ScheduleRow] = []
    for url in urls:
        try:
            ics_text = fetch_ics_schedule(url)
            events = parse_ics_schedule(ics_text)
        except requests.RequestException:
            continue

        for event in events:
            if event.kickoff < now:
                continue
            if target not in _simplify(event.home_team):
                continue
            candidates.append(
                ScheduleRow(
                    match_number="",
                    kickoff=event.kickoff,
                    home_team=event.home_team,
                    away_team=event.away_team,
                    competition="",
                    venue="",
                    season="",
                    result_label="",
                    score=None,
                    total_points=None,
                    set_scores=(),
                )
            )

    if not candidates:
        return None
    candidates.sort(key=lambda row: row.kickoff)
    return candidates[0]


def find_recent_matches_for_team(
    rows: Sequence[ScheduleRow],
    team_name: str,
    *,
    limit: int,
    reference: Optional[datetime] = None,
) -> List[ScheduleRow]:
    if not team_name:
        return []
    target = _simplify(team_name)
    now = reference or datetime.now(tz=BERLIN_TZ)
    relevant = [
        row
        for row in rows
        if row.is_finished
        and row.kickoff < now
        and (target == _simplify(row.home_team) or target == _simplify(row.away_team))
    ]
    relevant.sort(key=lambda row: row.kickoff, reverse=True)
    return relevant[:limit]


def fetch_schedule_pdf_links(page_url: str = SCHEDULE_PAGE_URL) -> Dict[str, str]:
    response = requests.get(page_url, headers=REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    links: Dict[str, str] = {}

    # 1️⃣ Alte, bekannte Links aus dem HTML (scoresheet/pdf/...)
    for anchor in soup.select("a[href]"):
        href = anchor["href"]
        if "scoresheet/pdf" not in href:
            continue
        match = re.search(r"/([0-9]{4})/?$", href)
        if not match:
            continue
        match_number = match.group(1)
        links[match_number] = href

    # 2️⃣ NEU: SAMSscore-Fallback (2025/26)
    #     nur ergänzen, wenn Matchnummer noch fehlt
    for match_number in list(links.keys()):
        pass  # nur zur Klarheit – nichts zu tun

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
            # SAMSscore-PDFs enthalten keine Aufstellungen
            # → leere Aufstellung zurückgeben statt Abbruch
            team_codes = {"A": "", "B": ""}
            return MatchLineups(
                match=ScheduleRow(
                    match_number="0",
                    kickoff=datetime.now(tz=BERLIN_TZ),
                    home_team="",
                    away_team="",
                    competition="",
                    venue="",
                    season="",
                    result_label="",
                    score=None,
                    total_points=None,
                    set_scores=(),
            ),
        pdf_url="",
        team_names=team_codes,
        sets=[],
        rosters={},
    )

        team_codes = _extract_team_codes(pdf.pages[0])
        rosters = _extract_rosters(pdf, team_codes)

        set_lineups: List[SetLineup] = []
        for table in tables:
            set_number = _detect_set_number(table)
            if set_number is None:
                continue
            lineups, scores = _extract_positions_from_table(table)
            if not lineups:
                continue
            set_lineups.append(SetLineup(number=set_number, lineups=lineups, scores=scores))

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
        score=None,
        total_points=None,
        set_scores=(),
    )
    return MatchLineups(
        match=dummy_match,
        pdf_url="",
        team_names=team_codes,
        sets=set_lineups,
        rosters=rosters,
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
) -> Tuple[Dict[str, List[str]], Dict[str, Optional[str]]]:
    rows = [[_clean_cell(cell) for cell in row] for row in table]
    header_info = _find_header_indices(rows)
    if header_info:
        (
            header_index,
            left_cols,
            right_cols,
            team_codes,
            left_score_idx,
            right_score_idx,
        ) = header_info
        for row in rows[header_index + 1 :]:
            left_values = _collect_positions(row, left_cols)
            right_values = _collect_positions(row, right_cols)
            if len(left_values) == 6 and len(right_values) == 6:
                scores: Dict[str, Optional[str]] = {}
                if left_score_idx is not None:
                    score = _extract_score_value(row, left_score_idx)
                    if score is not None:
                        scores[team_codes[0]] = score
                if right_score_idx is not None:
                    score = _extract_score_value(row, right_score_idx)
                    if score is not None:
                        scores[team_codes[1]] = score
                return (
                    {
                        team_codes[0]: left_values,
                        team_codes[1]: right_values,
                    },
                    scores,
                )

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
                return ({team_order[0]: left, team_order[1]: right}, {})
            return ({"left": left, "right": right}, {})

    return ({}, {})


def _find_header_indices(
    rows: Sequence[Sequence[str]],
) -> Optional[
    Tuple[
        int,
        List[int],
        List[int],
        Tuple[str, str],
        Optional[int],
        Optional[int],
    ]
]:
    for index, row in enumerate(rows):
        roman_cols = [i for i, value in enumerate(row) if value in {"I", "II", "III", "IV", "V", "VI"}]
        if len(roman_cols) >= 12:
            team_codes = _detect_codes_from_row(row)
            if team_codes is None and index > 0:
                team_codes = _detect_codes_from_row(rows[index - 1])
            if team_codes is None and index > 1:
                team_codes = _detect_codes_from_row(rows[index - 2])
            if team_codes is None:
                continue
            left_cols = roman_cols[:6]
            right_cols = roman_cols[6:12]
            score_indices = [i for i, value in enumerate(row) if value == "Punkte"]
            left_score_idx = score_indices[0] if score_indices else None
            right_score_idx = score_indices[1] if len(score_indices) > 1 else None
            return (
                index,
                left_cols,
                right_cols,
                team_codes,
                left_score_idx,
                right_score_idx,
            )
    return None


def _detect_codes_from_row(row: Sequence[str]) -> Optional[Tuple[str, str]]:
    text = " ".join(str(cell or "") for cell in row)
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


def _extract_score_value(row: Sequence[str], index: int) -> Optional[str]:
    if index < 0 or index >= len(row):
        return None
    value = _clean_cell(row[index])
    if not value:
        return None
    match = re.search(r"\b\d{1,2}\b", value)
    if match:
        return match.group(0)
    return None


def _extract_rosters(
    pdf: pdfplumber.PDF,
    team_codes: Dict[str, str],
) -> Dict[str, Dict[str, str]]:
    rosters: Dict[str, Dict[str, str]] = {code: {} for code in team_codes}
    if len(team_codes) < 2:
        return rosters

    roster_table: Optional[Sequence[Sequence[str]]] = None
    for page in pdf.pages:
        for table in page.extract_tables():
            if not table:
                continue
            header_text = " ".join(_normalize_cell(cell) for cell in table[0])
            if _looks_like_roster_header(header_text):
                roster_table = table
                break
        if roster_table:
            break

    if roster_table is None:
        return rosters

    codes = list(team_codes.keys())
    left_code, right_code = codes[0], codes[1]

    total_columns = len(roster_table[0])
    left_number_idx = total_columns - 6
    left_name_idx = total_columns - 5
    right_number_idx = total_columns - 3
    right_name_idx = total_columns - 2

    for row in roster_table[1:]:
        left_numbers = _split_numbers(_safe_get(row, left_number_idx))
        left_names = _split_names(_safe_get(row, left_name_idx))
        for number, name in zip(left_numbers, left_names):
            if number:
                rosters[left_code][number] = name

        right_numbers = _split_numbers(_safe_get(row, right_number_idx))
        right_names = _split_names(_safe_get(row, right_name_idx))
        for number, name in zip(right_numbers, right_names):
            if number:
                rosters[right_code][number] = name

    return rosters


def _safe_get(row: Sequence[str], index: int) -> Optional[str]:
    if index < 0:
        index = len(row) + index
    if index < 0 or index >= len(row):
        return None
    return row[index]


def _looks_like_roster_header(text: str) -> bool:
    if not text:
        return False
    normalized = text.replace("\n", " ")
    has_left = re.search(r"\bA\s+.+?\s+\d+/\d+", normalized)
    has_right = re.search(r"\bB\s+.+?\s+\d+/\d+", normalized)
    return bool(has_left and has_right)


def _split_numbers(value: Optional[str]) -> List[str]:
    if not value:
        return []
    text = _normalize_cell(value)
    return re.findall(r"\b\d{1,2}\b", text)


def _split_names(value: Optional[str]) -> List[str]:
    if not value:
        return []
    text = _normalize_cell(value, collapse_spaces=False)
    parts = re.split(r"[\n\r]+", text)
    names: List[str] = []
    for part in parts:
        cleaned = _clean_player_name(part)
        if cleaned:
            names.append(cleaned)
    return names


def _extract_number_from_label(label: Optional[str]) -> Optional[str]:
    if not label:
        return None
    match = re.search(r"\b(\d{1,2})\b", label)
    if match:
        return match.group(1)
    return None


def _normalize_cell(value: Optional[str], *, collapse_spaces: bool = True) -> str:
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ")
    if collapse_spaces:
        text = " ".join(text.replace("\n", " ").split())
    return text.strip()


def _clean_player_name(raw: str) -> str:
    text = raw.replace("\xa0", " ").replace("★", " ")
    text = text.strip()
    if not text:
        return ""
    parts = text.split()
    filtered: List[str] = []
    for part in parts:
        if len(part) <= 3 and part.isalpha() and part.isupper():
            continue
        filtered.append(part)
    cleaned = " ".join(filtered).strip()
    return cleaned


def _short_display_name(full_name: Optional[str]) -> Optional[str]:
    if not full_name:
        return None
    if "," in full_name:
        last_name = full_name.split(",", 1)[0].strip()
        return last_name or None
    parts = full_name.split()
    return parts[-1] if parts else None


def _resolve_setter_numbers(
    team_name: str,
    *,
    roster_dir: Path,
    cache: Dict[str, List[str]],
) -> List[str]:
    key = _simplify(team_name)
    if not key:
        return []
    if key in cache:
        return cache[key]

    try:
        roster = collect_team_roster(team_name, roster_dir)
    except Exception:
        cache[key] = []
        return cache[key]

    setter_numbers: set[str] = set()
    for member in roster:
        if member.is_official:
            continue
        role = (member.role or "").lower()
        if "zuspiel" not in role and "setter" not in role:
            continue
        number: Optional[str] = None
        if member.number_value is not None:
            number = str(member.number_value)
        else:
            number = _extract_number_from_label(member.number_label)
        if number:
            setter_numbers.add(number)

    cache[key] = sorted(
        setter_numbers,
        key=lambda value: (0, int(value)) if value.isdigit() else (1, value),
    )
    return cache[key]


def _collect_official_roster_names(
    team_name: str,
    *,
    roster_dir: Path,
    cache: Dict[str, Dict[str, str]],
) -> Dict[str, str]:
    key = _simplify(team_name)
    if not key:
        return {}
    if key in cache:
        return cache[key]

    try:
        roster = collect_team_roster(team_name, roster_dir)
    except Exception:
        cache[key] = {}
        return cache[key]

    number_to_name: Dict[str, str] = {}
    for member in roster:
        if member.is_official:
            continue
        number: Optional[str] = None
        if member.number_value is not None:
            number = str(member.number_value)
        else:
            number = _extract_number_from_label(member.number_label)
        if not number:
            continue
        cleaned_name = (member.name or "").strip()
        if not cleaned_name:
            continue
        number_to_name[number] = cleaned_name

    cache[key] = number_to_name
    return cache[key]


def _simplify_player_name_for_compare(value: str) -> str:
    normalized = value.lower()
    normalized = re.sub(r"[^a-zäöüß\s]", " ", normalized)
    return " ".join(normalized.split())


def _choose_preferred_player_name(
    pdf_name: Optional[str], official_name: Optional[str]
) -> Optional[str]:
    pdf_clean = (pdf_name or "").strip()
    official_clean = (official_name or "").strip()

    if official_clean:
        if not pdf_clean:
            return official_clean

        simplified_pdf = _simplify_player_name_for_compare(pdf_clean)
        simplified_official = _simplify_player_name_for_compare(official_clean)

        if simplified_pdf and simplified_official:
            if simplified_pdf == simplified_official:
                return official_clean
            ratio = difflib.SequenceMatcher(None, simplified_pdf, simplified_official).ratio()
            if ratio >= 0.6 or simplified_pdf in simplified_official or simplified_official in simplified_pdf:
                return official_clean

        if len(official_clean) > len(pdf_clean):
            return official_clean

    if pdf_clean:
        return pdf_clean
    if official_clean:
        return official_clean
    return None


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
        rosters=pdf_lineups.rosters,
    )


def build_lineup_dataset(
    *,
    limit: int = 2,
    schedule_csv_url: str = DEFAULT_SCHEDULE_URL,
    additional_schedule_csv_urls: Sequence[str] = DEFAULT_ADDITIONAL_SCHEDULE_URLS,
    schedule_ics_url: str = DEFAULT_SCHEDULE_ICS_URL,
    additional_schedule_ics_urls: Sequence[str] = DEFAULT_ADDITIONAL_SCHEDULE_ICS_URLS,
    schedule_page_url: str = SCHEDULE_PAGE_URL,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    pdf_cache_dir: Path = PDF_CACHE_DIR,
    roster_cache_dir: Path = ROSTER_CACHE_DIR,
    home_team: str = USC_CANONICAL_NAME,
) -> Dict[str, object]:
    urls: List[str] = [schedule_csv_url]
    for url in additional_schedule_csv_urls:
        if url and url not in urls:
            urls.append(url)

    schedule_rows: List[ScheduleRow] = []
    for url in urls:
        try:
            csv_text = fetch_schedule_csv(url)
        except requests.RequestException:
            continue
        schedule_rows.extend(parse_schedule(csv_text))

    schedule_rows.sort(key=lambda row: row.kickoff)

    recent_rows = find_recent_matches_for_home_team(schedule_rows, home_team, limit=limit)
    if not recent_rows:
        raise RuntimeError(f"Keine abgeschlossenen Spiele von {home_team} gefunden.")

    next_home_match = find_next_home_match_row(schedule_rows, home_team)
    if not next_home_match:
        next_home_match = find_next_home_match_from_ics(
            home_team=home_team,
            schedule_ics_url=schedule_ics_url,
            additional_schedule_ics_urls=additional_schedule_ics_urls,
        )
    if not next_home_match:
        raise RuntimeError(f"Kein zukünftiges Heimspiel von {home_team} gefunden.")

    opponent_name = next_home_match.away_team

    opponent_rows = find_recent_matches_for_team(
        schedule_rows,
        opponent_name,
        limit=limit,
    )

    pdf_links = fetch_schedule_pdf_links(schedule_page_url)

    match_requests: List[Tuple[str, ScheduleRow]] = [
        ("home", row) for row in recent_rows
    ]
    match_requests.extend(("opponent", row) for row in opponent_rows)

    if not match_requests:
        raise RuntimeError("Keine relevanten Spiele für die Aufstellungsanalyse gefunden.")

    cache: Dict[str, MatchLineups] = {}
    matches: List[Tuple[str, MatchLineups]] = []
    for focus, row in match_requests:
        pdf_url = pdf_links.get(row.match_number)
        if not pdf_url:
            pdf_url = (
                f"https://live.volleyball-bundesliga.de/2025-26/"
                f"SAMSscore/{row.match_number}.pdf"
         )
        pdf_path = pdf_cache_dir / f"{row.match_number}.pdf"
        if row.match_number not in cache:
            download_pdf(pdf_url, pdf_path)
            cache[row.match_number] = extract_lineups_from_pdf(pdf_path)
        pdf_lineups = cache[row.match_number]
        matches.append((focus, merge_schedule_details(row, pdf_url, pdf_lineups)))

    setter_cache: Dict[str, List[str]] = {}
    official_roster_cache: Dict[str, Dict[str, str]] = {}
    for _focus, match in matches:
        for name in match.team_names.values():
            _resolve_setter_numbers(name, roster_dir=roster_cache_dir, cache=setter_cache)
            _collect_official_roster_names(
                name, roster_dir=roster_cache_dir, cache=official_roster_cache
            )

    dataset = _serialize_dataset(
        matches,
        home_team=home_team,
        opponent_team=opponent_name,
        setter_lookup=setter_cache,
        roster_lookup=official_roster_cache,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    return dataset


def _serialize_dataset(
    matches: Sequence[Tuple[str, MatchLineups]],
    *,
    home_team: str,
    opponent_team: str,
    setter_lookup: Dict[str, List[str]],
    roster_lookup: Dict[str, Dict[str, str]],
) -> Dict[str, object]:
    serialized: List[Dict[str, object]] = []
    for focus, match in matches:
        # Team code for the configured home team from config.json
        configured_home_team_code = _find_team_code(match.team_names, home_team)
        opponent_code = _find_team_code(match.team_names, opponent_team) if opponent_team else None
        # Generic fallback: if still not found, check which scheduled team is the
        # configured home team and look up its PDF code accordingly.
        if configured_home_team_code is None:
            home_norm = _normalize_team_name(home_team)
            scheduled_home_norm = _normalize_team_name(match.match.home_team)
            scheduled_away_norm = _normalize_team_name(match.match.away_team)
            if (
                scheduled_home_norm == home_norm
                or home_norm in scheduled_home_norm
                or scheduled_home_norm in home_norm
            ):
                configured_home_team_code = _find_team_code(match.team_names, match.match.home_team)
            elif (
                scheduled_away_norm == home_norm
                or home_norm in scheduled_away_norm
                or scheduled_away_norm in home_norm
            ):
                configured_home_team_code = _find_team_code(match.team_names, match.match.away_team)
        if opponent_code is None and opponent_team:
            # The opponent in the scheduled match is the one that isn't the home team
            for code, name in match.team_names.items():
                if code != configured_home_team_code:
                    opponent_code = code
                    break
        home_code = _find_team_code(match.team_names, match.match.home_team)
        away_code = _find_team_code(match.team_names, match.match.away_team)

        focus_code: Optional[str] = None
        if focus == "home":
            focus_code = configured_home_team_code
        elif focus == "opponent":
            focus_code = None
            if opponent_team:
                target = _simplify(opponent_team)
                for code, name in match.team_names.items():
                    if _simplify(name) == target:
                        focus_code = code
                        break

        teams_meta: Dict[str, Dict[str, object]] = {}
        for code, name in match.team_names.items():
            normalized = name or ""
            simplified_team = _simplify(normalized)
            setters = setter_lookup.get(simplified_team, [])
            teams_meta[code] = {
                "code": code,
                "name": normalized,
                "is_focus": focus_code is not None and code == focus_code,
                # Match-local home marker (scheduled Mannschaft 1), not configured home team.
                "is_home": home_code is not None and code == home_code,
                "is_opponent": bool(opponent_team and _simplify(normalized) == _simplify(opponent_team)),
                "setters": list(setters),
            }

        schedule_set_scores = list(match.match.set_scores)
        serialized_sets: List[Dict[str, object]] = []
        for set_lineup in match.sets:
            lineups: Dict[str, List[Dict[str, Optional[str]]]] = {}
            for code, positions in set_lineup.lineups.items():
                roster = match.rosters.get(code, {})
                team_name = match.team_names.get(code, "")
                official_roster = roster_lookup.get(_simplify(team_name), {})
                entries: List[Dict[str, Optional[str]]] = []
                for slot, number in zip(POSITION_SLOTS, positions[:6]):
                    full_name = _choose_preferred_player_name(
                        roster.get(number), official_roster.get(number)
                    )
                    if not full_name:
                        full_name = roster.get(number) or official_roster.get(number)
                    short_name = _short_display_name(full_name)
                    entries.append(
                        {
                            "slot": slot,
                            "number": number,
                            "full_name": full_name,
                            "short_name": short_name,
                        }
                    )
                # Auffüllen, falls weniger als 6 Positionen erkannt wurden
                while len(entries) < 6:
                    slot = POSITION_SLOTS[len(entries)]
                    entries.append(
                        {
                            "slot": slot,
                            "number": None,
                            "full_name": None,
                            "short_name": None,
                        }
                    )
                lineups[code] = entries

            score_entries = {
                code: value
                for code, value in set_lineup.scores.items()
                if value is not None
            }
            score_label: Optional[str] = None
            if home_code and away_code:
                home_score = set_lineup.scores.get(home_code)
                away_score = set_lineup.scores.get(away_code)
                if home_score is not None and away_score is not None:
                    score_label = f"{home_score}:{away_score}"
                elif 0 < set_lineup.number <= len(schedule_set_scores):
                    fallback_label = schedule_set_scores[set_lineup.number - 1]
                    score_label = fallback_label
                    parts = fallback_label.split(":", 1)
                    if len(parts) == 2:
                        score_entries = {
                            home_code: parts[0],
                            away_code: parts[1],
                        }

            serialized_sets.append(
                {
                    "number": set_lineup.number,
                    "lineups": lineups,
                    "scores": score_entries,
                    "score_label": score_label,
                }
            )

        set_score_labels: List[str] = []
        if schedule_set_scores:
            set_score_labels.extend(schedule_set_scores)
        elif home_code and away_code:
            for set_lineup in match.sets:
                home_score = set_lineup.scores.get(home_code)
                away_score = set_lineup.scores.get(away_code)
                if home_score is None or away_score is None:
                    continue
                set_score_labels.append(f"{home_score}:{away_score}")

        result_value = match.match.score
        if not result_value:
            if match.match.result_label:
                result_value = match.match.result_label.split("/")[0].strip()
            else:
                result_value = ""

        serialized.append(
            {
                "focus": focus,
                "focus_team_code": focus_code,
                "focus_team_name": match.team_names.get(focus_code, opponent_team if focus == "opponent" else home_team),
                "match_number": match.match.match_number,
                "kickoff": match.match.kickoff.isoformat(),
                "date_label": match.match.kickoff.strftime("%d.%m.%Y"),
                "home_team": match.match.home_team,
                "away_team": match.match.away_team,
                "competition": match.match.competition,
                "venue": match.match.venue,
                "season": match.match.season,
                "result": result_value,
                "home_code": home_code,
                "away_code": away_code,
                "set_scores": set_score_labels,
                "pdf_url": match.pdf_url,
                "team_codes": match.team_names,
                "home_team_code": configured_home_team_code,
                "opponent_code": opponent_code,
                "teams": list(teams_meta.values()),
                "sets": serialized_sets,
            }
        )

    return {
        "generated_at": datetime.now(tz=BERLIN_TZ).isoformat(),
        "home_team": home_team,
        "opponent_team": opponent_team,
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
