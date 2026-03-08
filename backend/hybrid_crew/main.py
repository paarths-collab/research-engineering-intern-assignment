"""
hybrid_crew/main.py
--------------------
FastAPI entry point for the full research-style CrewAI pipeline.

Endpoints:
  POST /query          — run the 7-step full research pipeline
  GET  /health         — health check

Run with:
  uvicorn hybrid_crew.main:app --reload --port 8001
"""

import logging
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from hybrid_crew.pipeline import run_pipeline_sync

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Hybrid Crew Research Pipeline",
    description="Full research-style pipeline: Planner → Router → SQL/Vector → Forensic → Reviewer → Validator → Narrator",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    query: str


@app.post("/api/query")
async def query_endpoint(payload: QueryRequest):
    """
    Run the full research-style pipeline on the given query.
    Returns answer, route, plan, timing, validator, and reviewer results.
    """
    if not payload.query or not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    logger.info(f"[API] Received query: {payload.query}")

    import asyncio
    import concurrent.futures
    loop = asyncio.get_event_loop()
    try:
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = await loop.run_in_executor(pool, run_pipeline_sync, payload.query)
    except Exception as exc:
        logger.exception(f"[API] Pipeline error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

    return result


@app.get("/health")
async def health():
    return {"status": "ok", "pipeline": "hybrid_crew v2 (research-style)"}
