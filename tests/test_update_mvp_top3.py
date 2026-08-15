from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import requests


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "update_mvp_top3.py"
SPEC = importlib.util.spec_from_file_location("update_mvp_top3", SCRIPT_PATH)
assert SPEC and SPEC.loader
update_mvp_top3 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update_mvp_top3)


def test_build_dataset_keeps_failed_indicator_empty(monkeypatch, capsys) -> None:
    monkeypatch.setattr(update_mvp_top3, "get_viewstate", lambda session: ("viewstate", Mock()))
    monkeypatch.setattr(
        update_mvp_top3,
        "extract_indicators",
        lambda soup: {"failed": "Broken ranking", "working": "Working ranking"},
    )

    def fetch_indicator(session, indicator, viewstate, *, max_rows):
        if indicator == "failed":
            raise update_mvp_top3.MVPDatasetError("ranking table missing")
        return [{"Name": "Player"}], 2, "new-viewstate"

    monkeypatch.setattr(update_mvp_top3, "fetch_indicator", fetch_indicator)

    dataset = update_mvp_top3.build_dataset("USC Münster", "Dresdner SC")

    assert dataset["indicators"][0] == {
        "id": "failed",
        "label": "Broken ranking",
        "pages": 0,
        "all_players": [],
    }
    assert dataset["indicators"][1]["all_players"] == [{"Name": "Player"}]
    assert "Broken ranking" in capsys.readouterr().err


def test_main_preserves_existing_output_after_source_failure(monkeypatch, tmp_path, capsys) -> None:
    output_path = tmp_path / "mvp_top3.json"
    previous_dataset = {"generated_at": "previous successful run"}
    output_path.write_text(json.dumps(previous_dataset), encoding="utf-8")

    def fail_build(*args, **kwargs):
        raise requests.ConnectionError("source unavailable")

    monkeypatch.setattr(update_mvp_top3, "build_dataset", fail_build)

    update_mvp_top3.main(
        [
            "--home-team",
            "USC Münster",
            "--opponent-team",
            "Dresdner SC",
            "--output",
            str(output_path),
        ]
    )

    assert json.loads(output_path.read_text(encoding="utf-8")) == previous_dataset
    assert "MVP dataset was not updated" in capsys.readouterr().err
