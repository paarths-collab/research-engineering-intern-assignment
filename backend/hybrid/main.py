"""
hybrid/main.py
---------------
FastAPI application entry point — lives inside hybrid/ package.

Run from backend/:
    uvicorn hybrid.main:app --host 0.0.0.0 --port 8000 --reload

Endpoints:
    GET  /health   -> liveness + loaded views
    POST /query    -> main hybrid RAG query
    GET  /schema   -> dataset schema for debugging
    GET  /views    -> loaded DuckDB view names
"""

import sys
import io
import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path

# Force UTF-8 on Windows before any other import
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(r"C:\Users\Paarth\Coding\simppl\research-engineering-intern-assignment\backend\.env"))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from hybrid.database import get_db_connection, get_loaded_views
from hybrid.constants import VALID_SUBREDDITS, TABLE_SCHEMA, DATE_START, DATE_END
from hybrid.pipeline import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Startup ────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Startup: loading DuckDB views...")
    get_db_connection()
    loaded = get_loaded_views()
    logger.info(f"Loaded {len(loaded)} views: {loaded}")
    yield
    logger.info("Shutdown.")


app = FastAPI(
    title="Hybrid Narrative Intelligence API",
    description=(
        "LangChain multi-agent system for Reddit political narrative analysis. "
        "Orchestrator -> SQL/Vector agents -> Forensic synthesis."
    ),
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ──────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=5,
        max_length=600,
        description="Natural language question about the Reddit dataset.",
        examples=[
            "Which 2 authors had the highest final_influence_score?",
            "What narratives spread most between Conservative and politics?",
            "Which subreddit has the highest echo chamber score?",
        ],
    )


class QueryResponse(BaseModel):
    answer:     str
    route_used: str
    timing:     dict      = {}
    validator:  dict      = {}


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Liveness check. Returns loaded DuckDB view names."""
    loaded = get_loaded_views()
    return {
        "status":       "ok",
        "loaded_views": loaded,
        "view_count":   len(loaded),
        "date_range":   {"start": DATE_START, "end": DATE_END},
    }


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    Main hybrid RAG query endpoint.
    Routes to SQL / Vector / both based on query classification,
    then synthesises a grounded forensic answer.
    """
    logger.info(f"[API] /query -- '{request.query}'")
    try:
        result = await run_pipeline(request.query)
        return QueryResponse(
            answer=result["answer"],
            route_used=result["route_used"],
            timing=result.get("timing", {}),
            validator=result.get("validator", {}),
        )
    except Exception as exc:
        logger.exception(f"[API] Unhandled error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/schema")
async def schema():
    """Returns full dataset schema for debugging / frontend display."""
    return {
        "tables":           TABLE_SCHEMA,
        "valid_subreddits": sorted(VALID_SUBREDDITS),
        "date_range":       {"start": DATE_START, "end": DATE_END},
    }


@app.get("/views")
async def views():
    """Returns which DuckDB views were successfully loaded."""
    return {"loaded_views": get_loaded_views()}
