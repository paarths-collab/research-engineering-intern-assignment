from fastapi import APIRouter, HTTPException
from ..models.graph_models import SimulateRequest
from ..services.interaction_engine import simulate_graph

router = APIRouter(prefix="/api/perspective", tags=["perspective"])


@router.post("/simulate")
async def simulate(request: SimulateRequest):
    try:
        result = await simulate_graph(request.nodes, request.edges)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health():
    return {"status": "ok"}
