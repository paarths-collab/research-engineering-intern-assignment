"""
hybrid_chatbot/api.py
---------------------
FastAPI entrypoint for the deployable hybrid chatbot.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from api_security import APISecurityMiddleware

from .pipeline import ChatPipeline
from .llm_client import LLMClient

logger = logging.getLogger("hybrid_chatbot.api")

llm_client = LLMClient()

pipeline = ChatPipeline(llm_client)


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=8000)
    debug: bool = False
    web_search: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_resources()
    yield


app = FastAPI(title="Chatbot API", version="1.0.0", lifespan=lifespan)
app.add_middleware(APISecurityMiddleware, standalone=True)


@app.get("/health")
def health():
    sql = sql_health()
    return {
        "status": _overall_status(sql),
        "llm_ready": bool(llm_client.api_key),
        "web_search_ready": bool(pipeline.web.enabled),
        "sql": sql,
        "dataset_date_range": sql.get("date_range"),
    }


@app.post("/query")
def query(payload: QueryRequest):
    try:
        result = pipeline.run(payload.query, web_search=payload.web_search)
    except Exception as exc:
        logger.exception("Chatbot pipeline failed: %s", exc)
        raise HTTPException(status_code=500, detail="Chatbot request failed")

    if payload.debug:
        result["debug"] = {
            "llm_model": llm_client.model,
            "llm_base_url": llm_client.base_url,
            "web_search_enabled": payload.web_search,
        }
    else:
        # Raw internals are debug-only; provenance (dataset, evidence, answer_mode,
        # llm_used, retrieval) and `sql` are always returned.
        result.pop("route", None)
        result.pop("timing", None)
        result.pop("dataset_chunks", None)
        result.pop("web_articles", None)
    return result


def _overall_status(sql: dict) -> str:
    """Overall health: 'ok' only when SQL is fully ready, 'degraded' with some tables
    missing, 'unavailable' when no table could be served (HTTP 200 in every case)."""
    state = sql.get("state")
    if state == "ready":
        return "ok"
    if state == "degraded":
        return "degraded"
    return "unavailable"


def sql_health() -> dict:
    """SQL store status (initializing it if needed) plus the dataset date range."""
    store = pipeline.sql_store
    status = store.initialize().to_dict()
    try:
        start, end = store.dataset_date_range()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Dataset date range unavailable: %s", exc)
        start = end = None
    status["date_range"] = {
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
    }
    return status


def init_resources() -> dict:
    """Initialize chatbot resources (safe to call multiple times).

    Builds/opens the SQL store; failures are logged and recorded in the store status
    (surfaced by GET /health) rather than raised, so the app still starts.
    """
    try:
        status = pipeline.sql_store.initialize()
    except Exception as exc:  # noqa: BLE001 - never block startup
        logger.exception("Chatbot SQL initialization failed: %s", exc)
        return {"state": "unavailable", "error": str(exc)}
    if status.state == "ready":
        logger.info("Chatbot SQL ready (%d tables, storage=%s)", len(status.available_tables), status.storage)
    else:
        logger.warning(
            "Chatbot SQL %s: missing=%s error=%s", status.state, status.missing_tables, status.error
        )
    return status.to_dict()
