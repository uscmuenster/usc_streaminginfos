"""Helper utilities to talk to the Volleyball Bundesliga REST API."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, Iterator, List, Optional

import requests
from dateutil import parser

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class LeagueRanking:
    rank: int
    team_name: str
    matches_played: int
    wins: int
    losses: int
    points: int
    set_ratio: Optional[float]
    ball_ratio: Optional[float]


@dataclass(slots=True)
class LeagueMatch:
    uuid: str
    date: datetime
    team_home: str
    team_away: str
    venue: Optional[str]
    results: Optional[str]

    @property
    def is_finished(self) -> bool:
        return self.results is not None


class VblApi:
    """Minimal client for the Volleyball Bundesliga SAMS API."""

    BASE_URL = "https://www.volleyball-bundesliga.de/api/v2"

    def __init__(self, api_key: str, *, timeout: int = 30) -> None:
        self.api_key = api_key.strip()
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "usc_kommentatoren/1.0",
                "Accept": "application/json",
                "X-Api-Key": self.api_key,
            }
        )

    def _request(self, path: str, params: Optional[Dict[str, object]] = None) -> Dict:
        if not self.api_key:
            raise RuntimeError("A VBL API key is required to query league data.")
        url = f"{self.BASE_URL}{path}"
        response = self.session.get(url, params=params or {}, timeout=self.timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:  # pragma: no cover - network errors
            LOGGER.error("API request failed: %s", exc)
            raise
        return response.json()

    def _paginate(self, path: str, params: Optional[Dict[str, object]] = None) -> Iterator[Dict]:
        params = dict(params or {})
        page = 0
        while True:
            params["page"] = page
            params.setdefault("size", 100)
            payload = self._request(path, params=params)
            content = payload.get("content")
            if content is None and "_embedded" in payload:
                # HAL style embedding
                embedded = payload.get("_embedded") or []
                if isinstance(embedded, list):
                    content = embedded
            if not content:
                break
            for item in content:
                yield item
            if payload.get("last", True):
                break
            page += 1

    def find_league_by_name(self, name: str, *, season_uuid: Optional[str] = None) -> Optional[Dict]:
        params: Dict[str, object] = {}
        if season_uuid:
            params["season"] = season_uuid
        for item in self._paginate("/leagues", params=params):
            if str(item.get("name", "")).strip().lower() == name.strip().lower():
                return item
        return None

    def get_league_rankings(self, league_uuid: str) -> List[LeagueRanking]:
        data = self._request(f"/leagues/{league_uuid}/rankings", params={"size": 100})
        rows = data.get("content") or []
        rankings: List[LeagueRanking] = []
        for row in rows:
            set_ratio = self._parse_ratio(row.get("setRatio"))
            ball_ratio = self._parse_ratio(row.get("ballRatio"))
            rankings.append(
                LeagueRanking(
                    rank=int(row.get("rank", 0) or 0),
                    team_name=str(row.get("teamName", "")),
                    matches_played=int(row.get("matchesPlayed", 0) or 0),
                    wins=int(row.get("wins", 0) or 0),
                    losses=int(row.get("losses", 0) or 0),
                    points=int(row.get("points", 0) or 0),
                    set_ratio=set_ratio,
                    ball_ratio=ball_ratio,
                )
            )
        rankings.sort(key=lambda item: item.rank)
        return rankings

    def get_league_matches(self, league_uuid: str) -> List[LeagueMatch]:
        matches = list(
            self._paginate(
                "/league-matches",
                params={"for-league": league_uuid, "size": 100},
            )
        )
        return [self._match_from_payload(item) for item in matches]

    def get_team_matches(self, team_uuid: str) -> List[LeagueMatch]:
        matches = list(
            self._paginate(
                "/league-matches",
                params={"for-team": team_uuid, "size": 100},
            )
        )
        return [self._match_from_payload(item) for item in matches]

    def _match_from_payload(self, payload: Dict) -> LeagueMatch:
        date_str = payload.get("date")
        dt = parser.isoparse(date_str) if date_str else datetime.min
        venue = None
        if isinstance(payload.get("location"), dict):
            venue = payload["location"].get("name")
        results = None
        result_payload = payload.get("results")
        if isinstance(result_payload, dict) and result_payload.get("setPoints"):
            results = str(result_payload.get("setPoints"))
        return LeagueMatch(
            uuid=str(payload.get("uuid", "")),
            date=dt,
            team_home=str(payload.get("team1Description", "")),
            team_away=str(payload.get("team2Description", "")),
            venue=venue,
            results=results,
        )

    @staticmethod
    def _parse_ratio(value: Optional[object]) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            try:
                numerator, denominator = str(value).split(":", maxsplit=1)
                return float(numerator) / float(denominator)
            except Exception:  # pragma: no cover - defensive fallback
                LOGGER.debug("Could not parse ratio value: %s", value)
                return None
