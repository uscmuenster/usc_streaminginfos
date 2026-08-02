"""Zentrales Laden der Anwendungskonfiguration aus config.json."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

# Standard-Heimteam, wenn keine config.json vorhanden ist
DEFAULT_HOME_TEAM = "USC Münster"
_DEFAULT_HOME_TEAM = DEFAULT_HOME_TEAM  # Rückwärtskompatibilität

# Pfad zur config.json relativ zum Repository-Root (zwei Ebenen über diesem Modul)
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.json"


@dataclass(frozen=True)
class SeasonSourceConfig:
    """Eine Saison mit einem oder mehreren CSV-Spielplanexporten."""

    season: str
    urls: Tuple[str, ...]


@dataclass(frozen=True)
class AppConfig:
    """Anwendungskonfiguration aus config.json."""

    home_team: str
    theme_primary: Optional[str]
    schedule_csv_url: Optional[str] = None
    schedule_ics_url: Optional[str] = None
    schedule_page_url: Optional[str] = None
    comparison_seasons: Tuple[SeasonSourceConfig, ...] = ()


def _optional_string(data: object, key: str) -> Optional[str]:
    if not isinstance(data, dict):
        return None
    value = data.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _comparison_seasons(data: object) -> Tuple[SeasonSourceConfig, ...]:
    if not isinstance(data, list):
        return ()
    result = []
    for entry in data:
        season = _optional_string(entry, "season")
        raw_urls = entry.get("urls") if isinstance(entry, dict) else None
        urls = tuple(
            url.strip()
            for url in raw_urls or ()
            if isinstance(url, str) and url.strip()
        )
        if season and urls:
            result.append(SeasonSourceConfig(season=season, urls=urls))
    return tuple(result)


def load_config(path: Optional[Path] = None) -> AppConfig:
    """Lädt die Konfiguration aus *path* (Standard: config.json im Repo-Root).

    Bei fehlender oder ungültiger Datei wird eine Warnung ausgegeben und die
    Standardkonfiguration (USC Münster) zurückgegeben.
    """
    config_path = path or _DEFAULT_CONFIG_PATH

    if not config_path.exists():
        return AppConfig(home_team=_DEFAULT_HOME_TEAM, theme_primary=None)

    try:
        raw = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(
            f"Warnung: config.json konnte nicht gelesen werden ({exc}). "
            "Standardkonfiguration wird verwendet.",
            file=sys.stderr,
        )
        return AppConfig(home_team=_DEFAULT_HOME_TEAM, theme_primary=None)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(
            f"Warnung: config.json enthält ungültiges JSON ({exc}). "
            "Standardkonfiguration wird verwendet.",
            file=sys.stderr,
        )
        return AppConfig(home_team=_DEFAULT_HOME_TEAM, theme_primary=None)

    if not isinstance(data, dict):
        print(
            "Warnung: config.json hat unerwartetes Format (kein Objekt). "
            "Standardkonfiguration wird verwendet.",
            file=sys.stderr,
        )
        return AppConfig(home_team=_DEFAULT_HOME_TEAM, theme_primary=None)

    home_team = data.get("home_team")
    if not home_team or not isinstance(home_team, str) or not home_team.strip():
        home_team = _DEFAULT_HOME_TEAM
    else:
        home_team = home_team.strip()

    theme_primary: Optional[str] = None
    theme = data.get("theme")
    if isinstance(theme, dict):
        primary = theme.get("primary")
        if primary and isinstance(primary, str) and primary.strip():
            theme_primary = primary.strip()

    sources = data.get("data_sources")
    return AppConfig(
        home_team=home_team,
        theme_primary=theme_primary,
        schedule_csv_url=_optional_string(sources, "schedule_csv_url"),
        schedule_ics_url=_optional_string(sources, "schedule_ics_url"),
        schedule_page_url=_optional_string(sources, "schedule_page_url"),
        comparison_seasons=_comparison_seasons(
            sources.get("comparison_seasons") if isinstance(sources, dict) else None
        ),
    )
