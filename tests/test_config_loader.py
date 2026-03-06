"""Unit-Tests für den Config-Loader."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Sicherstellen, dass das src-Verzeichnis im Pfad liegt
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from usc_kommentatoren.config_loader import AppConfig, load_config, DEFAULT_HOME_TEAM


def test_load_config_default_when_no_file(tmp_path: Path) -> None:
    """Ohne config.json sollen USC-Defaults verwendet werden."""
    cfg = load_config(tmp_path / "does_not_exist.json")
    assert cfg.home_team == DEFAULT_HOME_TEAM
    assert cfg.theme_primary is None


def test_load_config_full(tmp_path: Path) -> None:
    """config.json mit home_team und theme.primary korrekt laden."""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"home_team": "Dresdner SC", "theme": {"primary": "#ff0000"}}),
        encoding="utf-8",
    )
    cfg = load_config(config_file)
    assert cfg.home_team == "Dresdner SC"
    assert cfg.theme_primary == "#ff0000"


def test_load_config_no_theme(tmp_path: Path) -> None:
    """config.json ohne theme.primary → theme_primary ist None."""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"home_team": "SSC Palmberg Schwerin"}),
        encoding="utf-8",
    )
    cfg = load_config(config_file)
    assert cfg.home_team == "SSC Palmberg Schwerin"
    assert cfg.theme_primary is None


def test_load_config_missing_home_team_uses_default(tmp_path: Path) -> None:
    """Wenn home_team fehlt, soll der Default verwendet werden."""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"theme": {"primary": "#aabbcc"}}),
        encoding="utf-8",
    )
    cfg = load_config(config_file)
    assert cfg.home_team == DEFAULT_HOME_TEAM
    assert cfg.theme_primary == "#aabbcc"


def test_load_config_invalid_json_uses_default(tmp_path: Path) -> None:
    """Bei ungültigem JSON soll der Default verwendet werden."""
    config_file = tmp_path / "config.json"
    config_file.write_text("{invalid json}", encoding="utf-8")
    cfg = load_config(config_file)
    assert cfg.home_team == DEFAULT_HOME_TEAM
    assert cfg.theme_primary is None


def test_load_config_empty_home_team_uses_default(tmp_path: Path) -> None:
    """Wenn home_team leer ist, soll der Default verwendet werden."""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"home_team": "   "}),
        encoding="utf-8",
    )
    cfg = load_config(config_file)
    assert cfg.home_team == DEFAULT_HOME_TEAM


def test_load_config_strips_whitespace(tmp_path: Path) -> None:
    """home_team und theme.primary sollen getrimmt werden."""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"home_team": "  VC Wiesbaden  ", "theme": {"primary": "  #123abc  "}}),
        encoding="utf-8",
    )
    cfg = load_config(config_file)
    assert cfg.home_team == "VC Wiesbaden"
    assert cfg.theme_primary == "#123abc"


def test_load_config_from_repo_root() -> None:
    """Standard-Pfad zeigt auf config.json im Repo-Root und ist lesbar."""
    cfg = load_config()
    # Die Datei existiert; sie enthält USC Münster als Default
    assert isinstance(cfg, AppConfig)
    assert cfg.home_team  # nicht leer
