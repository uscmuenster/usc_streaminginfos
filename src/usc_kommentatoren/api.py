"""FastAPI application exposing MVP ranking data."""
from __future__ import annotations

from typing import Iterable, List, Sequence

from fastapi import FastAPI, HTTPException, Query

from .mvp import MVP_INDICATORS, TEAM_RANKING_FILTERS, collect_mvp_rankings

app = FastAPI(title="Volleyball Bundesliga MVP API")


def _ensure_team_list(raw_teams: Sequence[str] | str) -> List[str]:
    """Normalize the incoming ``teams`` query argument."""

    if isinstance(raw_teams, str):
        candidates: Iterable[str] = raw_teams.split(",")
    else:
        candidates = raw_teams

    teams = [team.strip() for team in candidates if team and team.strip()]
    return teams


@app.get("/mvp")
def get_mvp_rankings(
    teams: Sequence[str] | str = Query(
        ..., description="Liste der Teams, z. B. Stuttgart,Münster"
    ),
    limit: int = Query(
        5,
        ge=1,
        le=25,
        description="Maximale Anzahl der Spieler:innen pro Team und Indikator.",
    ),
):
    """Return MVP rankings for the requested teams."""

    team_list = _ensure_team_list(teams)
    if not team_list:
        raise HTTPException(status_code=400, detail="Parameter 'teams' darf nicht leer sein.")

    rankings = collect_mvp_rankings(team_list, limit=limit)
    if not rankings:
        raise HTTPException(status_code=404, detail="Keine MVP-Daten für die angegebenen Teams gefunden.")

    return rankings


@app.get("/teams")
def get_teams() -> List[str]:
    """Return all supported team names."""

    return list(TEAM_RANKING_FILTERS.keys())


@app.get("/indicators")
def get_indicators() -> dict[str, str]:
    """Return all available MVP indicators."""

    return dict(MVP_INDICATORS)
