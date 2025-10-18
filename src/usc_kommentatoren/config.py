"""Configuration helpers for the usc_kommentatoren toolkit."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence

import yaml


@dataclass(slots=True)
class ApiConfig:
    """Settings required to communicate with the VBL API."""

    api_key: str
    league_uuid: str
    team_uuid: str
    season_uuid: Optional[str] = None


@dataclass(slots=True)
class NewsSource:
    """Definition of a single news source."""

    name: str
    url: str
    type: str = "rss"
    limit: int = 5
    tags: Sequence[str] = field(default_factory=tuple)


@dataclass(slots=True)
class AppConfig:
    """Root configuration model."""

    api: Optional[ApiConfig] = None
    news_sources: Sequence[NewsSource] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> "AppConfig":
        api_section = mapping.get("api")
        api_config: Optional[ApiConfig] = None
        if isinstance(api_section, Mapping):
            api_config = ApiConfig(
                api_key=str(api_section.get("api_key", "")).strip(),
                league_uuid=str(api_section.get("league_uuid", "")).strip(),
                team_uuid=str(api_section.get("team_uuid", "")).strip(),
                season_uuid=(
                    str(api_section.get("season_uuid", "")).strip() or None
                ),
            )

        sources_raw: Iterable[Mapping[str, object]] = []
        raw_sources = mapping.get("news_sources")
        if isinstance(raw_sources, Sequence):
            sources_raw = [item for item in raw_sources if isinstance(item, Mapping)]

        sources: List[NewsSource] = []
        for item in sources_raw:
            name = str(item.get("name", "")).strip()
            url = str(item.get("url", "")).strip()
            if not name or not url:
                continue
            source_type = str(item.get("type", "rss")).strip().lower() or "rss"
            limit_value = item.get("limit")
            try:
                limit = int(limit_value) if limit_value is not None else 5
            except (TypeError, ValueError):
                limit = 5
            tags_value = item.get("tags")
            if isinstance(tags_value, Sequence) and not isinstance(tags_value, (str, bytes)):
                tags = tuple(str(tag) for tag in tags_value)
            else:
                tags = tuple()
            sources.append(NewsSource(name=name, url=url, type=source_type, limit=limit, tags=tags))

        return cls(api=api_config, news_sources=tuple(sources))


def load_config(path: Path) -> AppConfig:
    """Load a configuration file from YAML."""

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, Mapping):
        raise ValueError("Configuration file must contain a mapping at the root.")
    return AppConfig.from_mapping(data)
