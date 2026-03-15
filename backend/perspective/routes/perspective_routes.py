from __future__ import annotations

from fastapi import APIRouter

from perspective.controllers.perspective_controller import (
    get_news_presets,
    get_personas,
    simulate_perspectives,
)
from perspective.models.schemas import PerspectiveSimulateRequest

router = APIRouter(prefix="", tags=["perspective"])


@router.get("/personas")
def list_personas():
    return get_personas()


@router.get("/news-presets")
def list_news_presets(limit: int = 15):
    return get_news_presets(limit=limit)


@router.post("/simulate")
def simulate(payload: PerspectiveSimulateRequest):
    return simulate_perspectives(payload)
