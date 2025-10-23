from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Mapping, MutableMapping, Sequence

def _add_src_to_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


_add_src_to_path()

from usc_kommentatoren.mvp import MVP_INDICATORS, TEAM_RANKING_FILTERS, collect_mvp_rankings
from usc_kommentatoren.report import normalize_name


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LINEUPS_PATH = REPO_ROOT / "docs" / "data" / "aufstellungen.json"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "docs" / "data" / "mvp_top3.json"


class MVPDatasetError(RuntimeError):
    """Raised when the MVP dataset cannot be generated."""


def _load_team_information(lineups_path: Path) -> tuple[str, str]:
    try:
        with lineups_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError as exc:  # pragma: no cover - defensive
        raise MVPDatasetError(
            f"Lineup dataset not found at '{lineups_path}'."
        ) from exc
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise MVPDatasetError(
            f"Lineup dataset at '{lineups_path}' is not valid JSON."
        ) from exc

    usc_team = str(payload.get("usc_team") or "USC Münster")
    opponent_team = payload.get("opponent_team")
    if not opponent_team:
        raise MVPDatasetError("Could not determine opponent team from lineup dataset.")

    return usc_team, str(opponent_team)


def _load_rankings_from_file(path: Path) -> Mapping[str, object]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:  # pragma: no cover - defensive
        raise MVPDatasetError(f"Rankings dataset not found at '{path}'.") from exc
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise MVPDatasetError(f"Rankings dataset at '{path}' is not valid JSON.") from exc


def _resolve_team_label(team_name: str) -> str:
    normalized = normalize_name(team_name)
    mapped = TEAM_RANKING_FILTERS.get(normalized)
    if mapped:
        return mapped
    parts = [part for part in team_name.replace("-", " ").split() if part]
    return parts[-1] if parts else team_name


def _rows_to_dicts(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> List[MutableMapping[str, str]]:
    cleaned_headers: List[str] = []
    for index, header in enumerate(headers):
        cleaned_headers.append(header if header else f"column_{index}")

    max_columns = max((len(row) for row in rows), default=len(cleaned_headers))
    while len(cleaned_headers) < max_columns:
        cleaned_headers.append(f"column_{len(cleaned_headers)}")

    data: List[MutableMapping[str, str]] = []
    for row in rows:
        values = list(row) + [""] * (len(cleaned_headers) - len(row))
        row_map: MutableMapping[str, str] = {
            header: value for header, value in zip(cleaned_headers, values)
        }

        ranking_value = _format_ranking(row_map, cleaned_headers, row)
        if ranking_value:
            row_map["ranking"] = ranking_value

        data.append(row_map)
    return data


def _format_ranking(
    row_map: Mapping[str, str],
    headers: Sequence[str],
    original_row: Sequence[str],
) -> str:
    header_index = {header: idx for idx, header in enumerate(headers)}

    def value_for(header: str) -> str:
        value = row_map.get(header)
        if value is not None and value.strip():
            return value.strip()
        index = header_index.get(header)
        if index is not None and index < len(original_row):
            return original_row[index].strip()
        return ""

    wert1 = value_for("Wert1")
    wertung = value_for("Wertung")

    if wert1 and wertung:
        return f"{wert1} | {wertung}"
    if wert1:
        return wert1
    return wertung


def _select_team_rows(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    team_label: str,
    *,
    limit: int,
) -> List[List[str]]:
    try:
        team_index = headers.index("Mannschaft")
    except ValueError:
        team_index = None

    filtered: List[List[str]] = []
    if team_index is not None:
        for row in rows:
            if len(row) > team_index and row[team_index] == team_label:
                filtered.append(list(row))
    else:
        filtered = [list(row) for row in rows]

    return _ensure_row_limit(filtered, headers, team_label, limit)


def _ensure_row_limit(
    rows: List[List[str]], headers: Sequence[str], team_label: str, limit: int
) -> List[List[str]]:
    limited = rows[:limit]
    placeholder = _build_placeholder_row(headers, team_label)
    while len(limited) < limit:
        limited.append(list(placeholder))
    return limited


def _build_placeholder_row(headers: Sequence[str], team_label: str) -> List[str]:
    placeholder = ["–"] * len(headers)
    try:
        team_index = headers.index("Mannschaft")
    except ValueError:
        return placeholder
    placeholder[team_index] = team_label
    return placeholder


def build_dataset(
    *,
    usc_team: str,
    opponent_team: str,
    limit: int = 3,
    rankings_data: Mapping[str, object] | None = None,
) -> Mapping[str, object]:
    usc_label = _resolve_team_label(usc_team)
    opponent_label = _resolve_team_label(opponent_team)

    if rankings_data is None:
        rankings = collect_mvp_rankings([usc_team, opponent_team], limit=limit)
    else:
        rankings = rankings_data

    indicators_payload = []
    for indicator_id, indicator_label in MVP_INDICATORS.items():
        indicator_data = rankings.get(indicator_label)
        if not indicator_data:
            indicators_payload.append(
                {
                    "id": indicator_id,
                    "label": indicator_label,
                    "usc": [],
                    "opponent": [],
                }
            )
            continue

        headers = indicator_data.get("headers", [])
        rows = indicator_data.get("rows", [])

        usc_rows = _select_team_rows(headers, rows, usc_label, limit=limit)
        opponent_rows = _select_team_rows(headers, rows, opponent_label, limit=limit)

        indicators_payload.append(
            {
                "id": indicator_id,
                "label": indicator_label,
                "usc": _rows_to_dicts(headers, usc_rows),
                "opponent": _rows_to_dicts(headers, opponent_rows),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "usc_team": usc_team,
        "opponent_team": opponent_team,
        "limit": limit,
        "indicators": indicators_payload,
    }


def dump_dataset(dataset: Mapping[str, object], *, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(dataset, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate MVP Top 3 dataset for USC and opponent.")
    parser.add_argument(
        "--usc-team",
        help="Override the USC team name.",
    )
    parser.add_argument(
        "--opponent-team",
        help="Override the opponent team name.",
    )
    parser.add_argument(
        "--lineups-path",
        type=Path,
        default=DEFAULT_LINEUPS_PATH,
        help="Path to the lineup dataset containing opponent information.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Destination for the MVP dataset.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Number of players per team and indicator.",
    )
    parser.add_argument(
        "--rankings-path",
        type=Path,
        help="Optional path to an existing MVP rankings dataset (JSON).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)

    usc_team = args.usc_team
    opponent_team = args.opponent_team

    if not usc_team or not opponent_team:
        usc_team_from_dataset, opponent_team_from_dataset = _load_team_information(args.lineups_path)
        usc_team = usc_team or usc_team_from_dataset
        opponent_team = opponent_team or opponent_team_from_dataset

    rankings_override = None
    if args.rankings_path:
        rankings_override = _load_rankings_from_file(args.rankings_path)

    dataset = build_dataset(
        usc_team=usc_team,
        opponent_team=opponent_team,
        limit=args.limit,
        rankings_data=rankings_override,
    )
    dump_dataset(dataset, output_path=args.output)


if __name__ == "__main__":
    main()
