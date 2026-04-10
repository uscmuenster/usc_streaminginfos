"""Tests für Quelltext-Parser in scripts/update_germany_vnl.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "update_germany_vnl.py"
    spec = importlib.util.spec_from_file_location("update_germany_vnl", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_extract_match_facts_reads_teams_place_and_time() -> None:
    module = load_module()
    html = """
    <a class="vbw-mu-scheduled vbw-mu__status-info-btn">
      <div class=vbw-mu__info>
        <div class=vbw-mu__info--details>Pool 1 - Week 1 - Women #9</div>
        <div class=vbw-mu__info--venue>
          <div class=vbw-mu__time-wrapper data-timeutc=00:00 data-timelocal=20:00 data-utc-datetime=2026-06-04T00:00:00Z>
          </div>
          <div class=vbw-mu__info--city>Quebec City</div>
          <div class=vbw-mu__info--country>Canada</div>
        </div>
      </div>
      <div class=vbw-mu__team__name>Canada</div>
      <div class=vbw-mu__team__name>Germany</div>
      <div class=vbw-mu__date--day>Thursday</div>
      <div class=vbw-mu__date--date>04 Jun, 2026</div>
    </a>
    """
    facts = module.extract_match_facts(html)
    assert "Teams: Canada vs Germany" in facts
    assert "Ort: Quebec City" in facts
    assert "Anpfiff Lokal: 20:00" in facts


def test_extract_head_to_head_facts_marks_missing_ssr_history() -> None:
    module = load_module()
    html = "<title>Canada-Germany Women VNL 2026 04.06.2026</title>"
    facts = module.extract_head_to_head_facts(html)
    assert "Match-Titel: Canada-Germany Women VNL 2026 04.06.2026" in facts
    assert "Historische Spiele: Nicht serverseitig im Quelltext enthalten" in facts
