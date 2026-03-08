"""
Reddit Media Ecosystem Dashboard — Backend
FastAPI + LiteLLM SDK (Groq)

Run:
    uvicorn main:app --reload --port 8000

Env:
    GROQ_API_KEY=gsk_...
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os

from polarize_1.data_loader import DataStore
from polarize_1.compute import (
    get_echo_scores,
    get_similarity_matrix,
    get_category_breakdown,
    get_top_domains,
    get_treemap_payload,
    get_subreddit_summary_payload,
)
from polarize_1.ai_brief import generate_brief

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Reddit Media Ecosystem API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Startup: load & cache all data once ──────────────────────────────────────

store = DataStore()


@app.on_event("startup")
def startup():
    store.load()
    print("✓ Data loaded")
    print(f"  Subreddits : {store.subreddits}")
    print(f"  Flow rows  : {len(store.flow_df)}")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "subreddits": store.subreddits}


@app.get("/subreddits")
def list_subreddits():
    """Return all subreddit names."""
    return {"subreddits": store.subreddits}


@app.get("/echo-scores")
def echo_scores():
    """
    Panel 1 — Echo Score per subreddit.
    Returns lift values sorted descending.
    """
    return {"scores": get_echo_scores(store)}


@app.get("/similarity")
def similarity_matrix():
    """
    Panel 2 — Cosine similarity matrix across all subreddits.
    Returns: { subreddits: [...], matrix: [[...], ...] }
    """
    return get_similarity_matrix(store)


@app.get("/category-breakdown/{subreddit}")
def category_breakdown(subreddit: str):
    """
    Panel 3 — Source type composition for one subreddit.
    Returns: [{ cat, count, pct }, ...]
    """
    if subreddit not in store.subreddits:
        raise HTTPException(404, f"Unknown subreddit: {subreddit}")
    return {"subreddit": subreddit, "breakdown": get_category_breakdown(store, subreddit)}


@app.get("/top-domains/{subreddit}")
def top_domains(subreddit: str, n: int = 5):
    """
    Top n distinctive domains for a subreddit (by lift).
    """
    if subreddit not in store.subreddits:
        raise HTTPException(404, f"Unknown subreddit: {subreddit}")
    return {"subreddit": subreddit, "domains": get_top_domains(store, subreddit, n)}


@app.get("/treemap/{subreddit}")
def treemap_payload(subreddit: str):
    """
    Hierarchical Media Ecosystem data for Treemap visualizations.
    Replaces separate category/domain charts with a single drill-down.
    """
    if subreddit not in store.subreddits:
        raise HTTPException(404, f"Unknown subreddit: {subreddit}")
    return get_treemap_payload(store, subreddit)


@app.get("/summary-payload/{subreddit}")
def summary_payload(subreddit: str):
    """
    The full structured payload sent to the LLM.
    Useful for debugging / showing the user what the AI receives.
    """
    if subreddit not in store.subreddits:
        raise HTTPException(404, f"Unknown subreddit: {subreddit}")
    return get_subreddit_summary_payload(store, subreddit)


class BriefRequest(BaseModel):
    subreddit: str


@app.post("/intelligence-brief")
async def intelligence_brief(req: BriefRequest):
    """
    Panel 4 — Generate an LLM intelligence brief for a subreddit.
    Requires GROQ_API_KEY in environment.
    """
    if req.subreddit not in store.subreddits:
        raise HTTPException(404, f"Unknown subreddit: {req.subreddit}")

    from dotenv import load_dotenv
    from pathlib import Path
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(dotenv_path=env_path)

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(500, "GROQ_API_KEY not set")

    payload = get_subreddit_summary_payload(store, req.subreddit)
    brief = await generate_brief(payload, api_key)
    return {"subreddit": req.subreddit, "brief": brief, "payload": payload}
