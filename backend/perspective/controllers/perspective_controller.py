from __future__ import annotations

import logging

from fastapi import HTTPException

from perspective.models.schemas import PerspectiveSimulateRequest
from perspective.services.simulator_service import PerspectiveSimulatorService

logger = logging.getLogger("perspective.controller")

service = PerspectiveSimulatorService()


def get_personas():
    return {"personas": service.list_personas()}


def get_news_presets(limit: int = 15):
    return {"news": service.list_news_presets(limit=limit)}


def simulate_perspectives(payload: PerspectiveSimulateRequest):
    if not payload.nodes:
        raise HTTPException(status_code=400, detail="At least one node is required")

    try:
        return service.simulate(payload)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Perspective simulation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Perspective simulation failed")
