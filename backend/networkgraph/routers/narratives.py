import os
import json
import logging
import httpx
from datetime import datetime, timezone
from typing import Optional, Annotated
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from networkgraph.database import get_db
from networkgraph.routers.utils import (
    _norm_nid, _parse_sequence, _get_filtered_narratives
)

log = logging.getLogger("sntis.narratives")
router = APIRouter()

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

@router.get("/narratives")
def get_narratives(
    min_authors: Annotated[int, Query(ge=0)] = 1,
    min_subreddits: Annotated[int, Query(ge=0)] = 0,
    start_date: Annotated[Optional[str], Query()] = None,
    end_date: Annotated[Optional[str], Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
):
    with get_db() as con:
        df = _get_filtered_narratives(con, min_authors, min_subreddits, start_date, end_date)
        df = df.head(limit)

        items = []
        for _, row in df.iterrows():
            items.append(
                {
                    "narrative_id": _norm_nid(row["narrative_id"]),
                    "title": row.get("representative_title") or "Untitled Narrative",
                    "representative_title": row.get("representative_title") or "Untitled Narrative",
                    "author_count": int(row.get("author_count") or 0),
                    "community_count": int(row.get("subreddit_count") or 0),
                    "subreddit_count": int(row.get("subreddit_count") or 0),
                    "spread_score": float(row.get("spread_score") or 0.0),
                    "primary_domain": row.get("primary_domain"),
                    "first_seen": str(row.get("first_seen")) if row.get("first_seen") else None,
                    "start_timestamp": str(row.get("start_timestamp")) if row.get("start_timestamp") else None,
                    "starter_author": str(row.get("starter_author") or "").strip() or None,
                    "starter_subreddit": str(row.get("starter_subreddit") or "").strip() or None,
                    "topic_cluster": str(row.get("topic_cluster")) if row.get("topic_cluster") is not None else None,
                    "topic_label": row.get("topic_label"),
                }
            )

        thresholds = {"3+": 3, "4+": 4, "5+": 5, "6+": 6, "10+": 10}
        tabs = {k: [it for it in items if it["author_count"] >= v] for k, v in thresholds.items()}

        return {"items": items, "tabs": tabs, "total": len(items)}

@router.get("/narrative/{narrative_id}/overlay")
def get_narrative_overlay(narrative_id: str):
    with get_db() as con:
        nid = _norm_nid(narrative_id)
        row = con.execute("SELECT spread_sequence FROM chains WHERE narrative_id = ? LIMIT 1", [nid]).fetchone()
        if not row:
            return {"narrative_id": narrative_id, "edges": []}

        seq = _parse_sequence(row[0])
        if len(seq) < 2:
            return {"narrative_id": narrative_id, "edges": []}

        edges = []
        for idx in range(len(seq) - 1):
            src = seq[idx]
            tgt = seq[idx + 1]
            if src == tgt:
                continue
            edges.append(
                {
                    "source": f"sub::{src}",
                    "target": f"sub::{tgt}",
                    "sequence_index": idx + 1,
                    "timestamp": None,
                }
            )

        return {"narrative_id": narrative_id, "edges": edges}

@router.post("/narrative/{narrative_id}/analyze")
async def analyze_narrative(narrative_id: str):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured.")

    with get_db() as con:
        nid = _norm_nid(narrative_id)
        narr = con.execute(
            """
            SELECT narrative_id, cluster_id, representative_title, primary_domain,
                   unique_authors, unique_subreddits_x, spread_strength, first_seen_x, last_seen
            FROM narratives
            WHERE narrative_id = ?
            LIMIT 1
            """,
            [nid],
        ).fetchone()
        if not narr:
            raise HTTPException(status_code=404, detail=f"Narrative '{narrative_id}' not found.")

        # SQL Fix: Use subreddit_edges instead of joining posts (which lacks cluster_id)
        top_posts = con.execute(
            """
            SELECT title, subreddit, author, domain, score, num_comments, created_datetime, url
            FROM subreddit_edges
            WHERE narrative_id = ?
            ORDER BY score DESC, num_comments DESC
            LIMIT 12
            """,
            [nid],
        ).fetchall()

        subreddits = [r[0] for r in con.execute(
            "SELECT subreddit FROM subreddit_edges WHERE narrative_id = ? GROUP BY subreddit ORDER BY COUNT(*) DESC LIMIT 12",
            [nid],
        ).fetchall()]
        
        authors = [r[0] for r in con.execute(
            "SELECT author FROM subreddit_edges WHERE narrative_id = ? GROUP BY author ORDER BY COUNT(*) DESC LIMIT 12",
            [nid],
        ).fetchall()]
        
        domains = [r[0] for r in con.execute(
            "SELECT domain FROM subreddit_edges WHERE narrative_id = ? AND domain IS NOT NULL AND domain<>'' GROUP BY domain ORDER BY COUNT(*) DESC LIMIT 10",
            [nid],
        ).fetchall()]
        
        timeline = con.execute(
            """
            SELECT created_datetime::DATE AS date, COUNT(*) AS post_count
            FROM subreddit_edges
            WHERE narrative_id = ?
            GROUP BY 1
            ORDER BY 1
            """,
            [nid],
        ).fetchall()
        
        chain_row = con.execute("SELECT spread_sequence FROM chains WHERE narrative_id=? LIMIT 1", [nid]).fetchone()
        spread_path = _parse_sequence(chain_row[0]) if chain_row else []

        prompt = f"""You are a senior narrative intelligence analyst.
Analyze this narrative context from database records and provide a detailed investigation brief.

Return plain text with these exact sections:
Narrative Summary
Propagation Pattern
Amplification Actors
Source Influence
Timeline of Events
Potential Impact

Context:
- Narrative ID: {nid}
- Title: {narr[2]}
- Primary domain: {narr[3]}
- Unique authors: {narr[4]}
- Unique subreddits: {narr[5]}
- Spread score: {narr[6]}
- First seen: {narr[7]}
- Last seen: {narr[8]}

Top Reddit Posts:
{json.dumps([{"title": p[0], "subreddit": p[1], "author": p[2], "domain": p[3], "score": p[4], "comments": p[5], "created": str(p[6]), "url": p[7]} for p in top_posts], ensure_ascii=False)}

Subreddits involved:
{json.dumps(subreddits, ensure_ascii=False)}

Authors involved:
{json.dumps(authors, ensure_ascii=False)}

Domains used:
{json.dumps(domains, ensure_ascii=False)}

Spread path:
{json.dumps(spread_path, ensure_ascii=False)}

Timeline:
{json.dumps([{"date": str(t[0]), "post_count": int(t[1])} for t in timeline], ensure_ascii=False)}
"""

        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                GROQ_API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 900,
                    "temperature": 0.2,
                },
            )
            resp.raise_for_status()
            report = resp.json()["choices"][0]["message"]["content"].strip()

        return {
            "narrative_id": nid,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "report": report,
            "context": {
                "subreddits": subreddits,
                "authors": authors,
                "domains": domains,
                "spread_path": spread_path,
                "timeline": [{"date": str(t[0]), "post_count": int(t[1])} for t in timeline],
            },
        }
