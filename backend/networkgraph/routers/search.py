import os
import hashlib
import logging
import httpx
from collections import defaultdict, Counter
from typing import Optional, Annotated
from fastapi import APIRouter, Query, HTTPException

from networkgraph.database import get_db
from networkgraph.routers.utils import (
    NODE_COLORS, EDGE_COLORS, _edge_width, MAX_DOMAINS_PER_SUB, MAX_AUTHORS_PER_SUB
)
from networkgraph.models.schemas import AnalyzeNodeRequest, AnalyzeNodeResponse

log = logging.getLogger("sntis.search")
router = APIRouter()

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

def _build_node_prompt(node_type: str, node_id: str, ctx: Optional[dict]) -> str:
    if not isinstance(ctx, dict):
        ctx = {}
    if node_type == "subreddit":
        return f"Analyze r/{node_id}. Domains: {ctx.get('top_domains')}. Neighbors: {ctx.get('neighbor_subreddits')}. Task: community intelligence brief (4-6 sentences). End with Propagation Role."
    if node_type == "domain":
        return f"Analyze domain {node_id}. Usage: {ctx.get('subreddits_using')}. Task: source intelligence brief. End with Source Role."
    if node_type in ["author", "author_cluster"]:
        return f"Analyze u/{node_id}. Activity: {ctx.get('subreddits')}. Task: amplifier intelligence brief. End with Amplifier Role."
    return f"Analyze {node_id}"

@router.post("/analyze", response_model=AnalyzeNodeResponse, summary="AI node intelligence brief")
async def analyze_node(req: AnalyzeNodeRequest):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(503, "GROQ_API_KEY not configured.")
    prompt = _build_node_prompt(req.node_type, req.node_id, req.context_data)
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                GROQ_API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": GROQ_MODEL, "messages": [{"role": "user", "content": prompt}]},
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            return AnalyzeNodeResponse(analysis=raw, risk_level="Analyzed", key_points=[])
    except Exception as e:
        log.error("AI Error: %s", e)
        raise HTTPException(502, f"AI Error: {e}")

@router.get("/search")
def search_intelligence(
    q: Annotated[str, Query(min_length=2)],
    limit: Annotated[int, Query(ge=5, le=200)] = 50,
    mode: Annotated[str, Query(pattern="^(spread|sources|amplifiers|all)$")] = "all",
):
    with get_db() as con:
        # User Fix: Search only narratives table for the core request
        search_term = f"%{q}%"
        narratives_query = """
            SELECT 
                narrative_id, 
                representative_title, 
                primary_domain, 
                spread_strength,
                unique_authors,
                unique_subreddits_x
            FROM narratives
            WHERE lower(representative_title) LIKE lower(?)
            ORDER BY spread_strength DESC
            LIMIT ?
        """
        # Ensure exactly two parameters (term, limit) are passed if the limit is used in SQL
        narrative_rows = con.execute(narratives_query, [search_term, 25]).fetchall()
        
        if not narrative_rows:
            return {"nodes": [], "edges": [], "keyword_stats": [], "summary": {"posts": 0, "communities": 0, "connections": 0}}

        narrative_ids = [str(r[0]) for r in narrative_rows]
        narrative_ids_sql = "', '".join([v.replace("'", "''") for v in narrative_ids])

        nodes = []
        node_ids = set()
        
        def add_search_node(node):
            if node["id"] not in node_ids:
                node_ids.add(node["id"])
                nodes.append(node)

        # Get relevant subreddits from these narratives using subreddit_edges
        sub_counts = con.execute(f"""
            SELECT subreddit, COUNT(*) as post_count
            FROM subreddit_edges
            WHERE narrative_id IN ('{narrative_ids_sql}')
            GROUP BY subreddit
            ORDER BY post_count DESC
            LIMIT 50
        """).fetchall()
        
        total_posts_in_search = sum(int(r[1]) for r in sub_counts)

        for sub, count in sub_counts:
            size = float(max(20, min(50, 20 + (count / max(1, total_posts_in_search)) * 100)))
            add_search_node({
                "id": f"sub::{sub}",
                "label": sub,
                "type": "subreddit",
                "shape": "dot",
                "size": size,
                "color": NODE_COLORS["subreddit"],
                "font": {"color": "#ffffff", "size": 12, "background": "rgba(0,0,0,0.4)"},
                "metadata": {
                    "posts": int(count),
                    "percent": f"{(count/max(1, total_posts_in_search))*100:.1f}%"
                }
            })

        edges = []
        dom_freq = defaultdict(int)

        if mode in ("spread", "all"):
            edges_query = f"""
                SELECT origin_subreddit, subreddit, COUNT(*) as weight
                FROM subreddit_edges
                WHERE narrative_id IN ('{narrative_ids_sql}')
                  AND origin_subreddit IS NOT NULL
                  AND origin_subreddit <> subreddit
                GROUP BY 1, 2
                LIMIT 200
            """
            edge_rows = con.execute(edges_query).fetchall()
            
            for src, tgt, weight in edge_rows:
                src_str, tgt_str, w_int = str(src), str(tgt), int(weight or 0)
                eid = hashlib.md5(f"search::{src_str}::{tgt_str}".encode()).hexdigest()[:12]
                edges.append({
                    "id": eid,
                    "from": f"sub::{src_str}",
                    "to": f"sub::{tgt_str}",
                    "edge_type": "spread",
                    "color": {"color": EDGE_COLORS["spread"], "opacity": 0.4},
                    "width": float(_edge_width(w_int)),
                    "arrows": "to",
                    "title": f"Spread Flow: {w_int}"
                })
        if mode in ("sources", "all"):
            rows = con.execute(
                f"""
                SELECT subreddit, domain, COUNT(*) AS cnt
                FROM subreddit_edges
                WHERE narrative_id IN ('{narrative_ids_sql}')
                  AND domain IS NOT NULL AND domain <> ''
                GROUP BY 1, 2
                ORDER BY cnt DESC
                LIMIT 200
                """
            ).fetchall()

            per_sub = defaultdict(list)
            for sub, dom, cnt in rows:
                per_sub[str(sub)].append((str(dom), int(cnt)))

            for sub, pairs in per_sub.items():
                sub_str = str(sub)
                for dom, cnt in sorted(pairs, key=lambda x: x[1], reverse=True)[:5]:
                    dom_str, c_int = str(dom), int(cnt)
                    eid = hashlib.md5(f"sd::{sub_str}::{dom_str}".encode()).hexdigest()[:12]
                    edges.append({
                        "id": eid,
                        "from": f"sub::{sub_str}",
                        "to": f"dom::{dom_str}",
                        "edge_type": "source",
                        "color": {"color": EDGE_COLORS["source"], "opacity": 0.35},
                        "width": float(_edge_width(c_int)),
                        "title": f"r/{sub_str} -> {dom_str} ({c_int})",
                        "arrows": "to",
                    })
                    dom_freq[dom_str] += c_int
                    add_search_node({
                        "id": f"dom::{dom_str}",
                        "label": dom_str,
                        "type": "domain", "shape": "triangle", "size": 24,
                        "color": NODE_COLORS["domain"],
                        "font": {"color": "#ffffff", "size": 11},
                    })
        if mode in ("amplifiers", "all"):
            rows = con.execute(
                f"""
                SELECT author, subreddit, COUNT(*) AS cnt
                FROM subreddit_edges
                WHERE narrative_id IN ('{narrative_ids_sql}')
                  AND author IS NOT NULL AND author <> ''
                GROUP BY 1, 2
                ORDER BY cnt DESC
                LIMIT 200
                """
            ).fetchall()

            for author, sub, cnt in rows:
                auth_str, sub_str, cnt_int = str(author), str(sub), int(cnt)
                eid = hashlib.md5(f"as::{auth_str}::{sub_str}".encode()).hexdigest()[:12]
                edges.append({
                    "id": eid,
                    "from": f"aut::{auth_str}",
                    "to": f"sub::{sub_str}",
                    "edge_type": "amplifier",
                    "color": {"color": EDGE_COLORS["amplifier"], "opacity": 0.35},
                    "width": float(_edge_width(cnt_int)),
                    "arrows": "to",
                })
                add_search_node({
                    "id": f"aut::{auth_str}",
                    "label": auth_str,
                    "type": "author", "shape": "square", "size": 20,
                    "color": NODE_COLORS["author"],
                    "font": {"color": "#ffffff", "size": 10},
                })

        # Keyword stats from titles
        stats_rows = con.execute(f"SELECT title FROM subreddit_edges WHERE narrative_id IN ('{narrative_ids_sql}') LIMIT 500").fetchall()
        words = []
        stop_words = {'a', 'the', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'with', 'from', 'by', 'of', 'is', 'are', 'was', 'were', 'that', 'this', 'it', 'its', 'as', 'but', 'not'}
        for (t,) in stats_rows:
            if t:
                for w in t.lower().split():
                    w_clean = "".join(filter(str.isalnum, w))
                    if len(w_clean) > 3 and w_clean not in stop_words:
                        words.append(w_clean)
        
        top_words = Counter(words).most_common(10)
        keyword_stats = [{"keyword": w, "count": c} for w, c in top_words]
        top_sources = sorted([{"domain": d, "count": f} for d, f in dom_freq.items()], key=lambda x: x["count"], reverse=True)[:10]

        return {
            "nodes": nodes, "edges": edges, "keyword_stats": keyword_stats, "top_sources": top_sources,
            "summary": {"posts": total_posts_in_search, "communities": len(sub_counts), "connections": len(edges)}
        }
