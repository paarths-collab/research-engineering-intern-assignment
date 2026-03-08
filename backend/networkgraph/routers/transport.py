"""
routers/transport.py — Layer 2 Directed Narrative Transport View

Endpoint:
  GET /transport/{narrative_id}   → ordered transport chain for one narrative
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from networkgraph.data.loader import get_store, DataStore
from networkgraph.models.schemas import TransportChainResponse, TransportStep

router = APIRouter(prefix="/transport", tags=["transport"])
log = logging.getLogger("sntis.transport")


def _safe(val, cast=None):
    if pd.isna(val):
        return None
    try:
        return cast(val) if cast else val
    except Exception:
        return None


@router.get(
    "/{narrative_id}",
    response_model=TransportChainResponse,
    summary="Directed spread chain for a narrative",
)
def get_transport_chain(
    narrative_id: str,
    store: DataStore = Depends(get_store),
):
    """
    Layer 2 — Micro view.

    Returns the ordered spread chain for a given narrative_id.
    Each step is enriched with score/title/url from the edge table.

    Sort order: step_number ASC (deterministic — no ambiguity).
    """
    # ── Filter chain table ──────────────────────────────────────────────────
    chain_df = store.chains_df[
        store.chains_df["narrative_id"].astype(str) == narrative_id
    ].copy()

    if chain_df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No transport chain found for narrative_id='{narrative_id}'."
        )

    # Sort by step_number ascending
    if "step_number" in chain_df.columns:
        chain_df = chain_df.sort_values("step_number", ascending=True)
    else:
        log.warning("No step_number column in chains_df — using row order.")

    # ── Build a quick lookup from edge table (same narrative_id) ────────────
    edge_df = store.edges_df[
        store.edges_df["narrative_id"].astype(str) == narrative_id
    ]

    # Key: (subreddit, author) -> edge row for enrichment
    edge_lookup: dict = {}
    for _, erow in edge_df.iterrows():
        key = (str(erow.get("subreddit", "")), str(erow.get("author", "")))
        edge_lookup[key] = erow

    # ── Build chain steps ───────────────────────────────────────────────────
    steps = []
    for _, row in chain_df.iterrows():
        subreddit = str(row.get("subreddit", ""))
        author = str(row.get("author", ""))

        # Enrich from edge table
        erow = edge_lookup.get((subreddit, author), {})

        dt = row.get("created_datetime")
        if hasattr(dt, "isoformat"):
            dt_str = dt.isoformat()
        elif dt and pd.notna(dt):
            dt_str = str(dt)
        else:
            dt_str = None

        steps.append(TransportStep(
            step_number=int(row.get("step_number", 0)),
            subreddit=subreddit,
            author=author,
            created_datetime=dt_str,
            hours_from_origin=_safe(row.get("hours_from_origin"), float),
            score=_safe(erow.get("score"), float) if erow is not None else None,
            title=_safe(erow.get("title")) if erow is not None else None,
            url=_safe(erow.get("url")) if erow is not None else None,
        ))

    # Origin subreddit = first step's subreddit
    origin = steps[0].subreddit if steps else None

    return TransportChainResponse(
        narrative_id=narrative_id,
        total_steps=len(steps),
        origin_subreddit=origin,
        chain=steps,
    )


@router.get(
    "",
    summary="List all narrative IDs that have transport chains",
)
def list_narratives_with_chains(store: DataStore = Depends(get_store)):
    """Returns all unique narrative_ids that have an entry in the chain table."""
    ids = store.chains_df["narrative_id"].astype(str).unique().tolist()
    return {"narrative_ids": ids, "count": len(ids)}
