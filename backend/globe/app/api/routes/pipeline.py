import asyncio
from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.pipeline.orchestrator import run_pipeline, get_current_status
from app.utils.logger import get_logger

router = APIRouter(prefix="/pipeline", tags=["pipeline"])
logger = get_logger(__name__)

_pipeline_lock = asyncio.Lock()


@router.post("/run")
async def trigger_pipeline(background_tasks: BackgroundTasks):
    """Trigger a full pipeline run in the background."""
    if _pipeline_lock.locked():
        status = get_current_status()
        return {
            "message": "Pipeline already running",
            "run_id": status.run_id if status else None,
            "status": status.status if status else "unknown",
        }

    async def _run():
        async with _pipeline_lock:
            await run_pipeline()

    background_tasks.add_task(_run)
    return {"message": "Pipeline started", "status": "running"}


@router.get("/status")
async def pipeline_status():
    """Current pipeline run status."""
    status = get_current_status()
    if not status:
        return {"status": "idle", "message": "No pipeline run recorded yet."}
    return status.model_dump()


@router.post("/run/sync")
async def trigger_pipeline_sync():
    """Run pipeline synchronously (for testing/debugging)."""
    if _pipeline_lock.locked():
        raise HTTPException(status_code=409, detail="Pipeline already running")

    async with _pipeline_lock:
        result = await run_pipeline()
    return result.model_dump()
