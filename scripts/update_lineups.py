#!/usr/bin/env python3
"""Hilfsprogramm zum Aktualisieren der Aufstellungsdaten."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _add_src_to_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Lädt die letzten USC-Spielberichtsbögen sowie die jüngsten Partien des "
            "nächsten Gegners und erzeugt den Lineup-Datensatz."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=2,
        help="Anzahl der abgeschlossenen USC-Spiele, die ausgewertet werden (Standard: 2).",
    )
    parser.add_argument(
        "--schedule-url",
        default=None,
        help="Optionaler Override für die CSV-Export-URL des Spielplans.",
    )
    parser.add_argument(
        "--schedule-page-url",
        default=None,
        help="Optionaler Override für die HTML-Spielplanseite mit den PDF-Links.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Pfad für die erzeugte JSON-Datei (Standard: docs/data/aufstellungen.json).",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Zwischenspeicher für heruntergeladene PDF-Dateien (Standard: data/lineups).",
    )
    parser.add_argument(
        "--roster-dir",
        type=Path,
        default=None,
        help="Zwischenspeicher für offizielle Kaderexporte (Standard: data/rosters).",
    )
    return parser


def main() -> int:
    _add_src_to_path()
    from usc_kommentatoren import lineups

    parser = build_parser()
    args = parser.parse_args()

    dataset = lineups.build_lineup_dataset(
        limit=args.limit,
        schedule_csv_url=args.schedule_url or lineups.DEFAULT_SCHEDULE_URL,
        schedule_page_url=args.schedule_page_url or lineups.SCHEDULE_PAGE_URL,
        output_path=args.output or lineups.DEFAULT_OUTPUT_PATH,
        pdf_cache_dir=args.cache_dir or lineups.PDF_CACHE_DIR,
        roster_cache_dir=args.roster_dir or lineups.ROSTER_CACHE_DIR,
    )

    print(
        "Datensatz aktualisiert:",
        f"{len(dataset['matches'])} Spiele",
        f"-> {args.output or lineups.DEFAULT_OUTPUT_PATH}",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - manuelle Ausführung
    raise SystemExit(main())
