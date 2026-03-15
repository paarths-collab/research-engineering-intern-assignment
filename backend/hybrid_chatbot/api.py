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

from .pipeline import ChatPipeline
from .llm_client import LLMClient

logger = logging.getLogger("hybrid_chatbot.api")

llm_client = LLMClient()

pipeline = ChatPipeline(llm_client)


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    debug: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_resources()
    yield


app = FastAPI(title="Chatbot API", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "llm_ready": bool(llm_client.api_key)}


@app.post("/query")
def query(payload: QueryRequest):
    try:
        result = pipeline.run(payload.query)
    except Exception as exc:
        logger.exception("Chatbot pipeline failed: %s", exc)
        raise HTTPException(status_code=500, detail="Chatbot request failed")

    if payload.debug:
        result["debug"] = {"llm_model": llm_client.model, "llm_base_url": llm_client.base_url}
    return result


def init_resources() -> None:
    """Initialize chatbot resources (safe to call multiple times)."""
    # LLM-only mode: no SQL/vector startup required.
    return
