import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/data/dvv_vnl_2026.json"
BUILDER = ROOT / "scripts/build_dvv_vnl.py"


def test_vnl_detail_data_contains_dates_and_libera_records():
    data = json.loads(DATA.read_text(encoding="utf-8"))

    assert [week["date"] for week in data["weeks"]] == [
        "4.–7. Juni 2026",
        "17.–21. Juni 2026",
        "8.–12. Juli 2026",
    ]
    players = {player["name"]: player for player in data["players"]}
    assert players["Patricia Nestler"]["matches"] == "8"
    assert players["Emma Sambale"]["matches"] == "4"
    assert all(players[name]["source"].startswith("https://en.volleyballworld.com/") for name in ("Patricia Nestler", "Emma Sambale"))


def test_builder_renders_requested_context(tmp_path):
    output = tmp_path / "vnl.html"
    subprocess.run(
        [sys.executable, str(BUILDER), "--data", str(DATA), "--output", str(output)],
        check=True,
    )
    page = output.read_text(encoding="utf-8")

    for expected in (
        "22.–26. Juli 2026 in Macao",
        "East Asian Games Dome",
        "sieben besten Teams der Vorrunde",
        "26. Juli · Türkiye – Brasilien 3:1",
        "Qualität im ersten und zweiten Kontakt",
        "VBL-Wechselbörse – letztes Update 10.08.2026",
        'href="https://volleyball-streaming-ms.de/dvv_laenderspiele_20260516.html"',
    ):
        assert expected in page
    assert 'href="dvv_laenderspiele_20260516.html"' not in page
