import logging
import hashlib
from collections import defaultdict
from typing import Optional, Annotated
from fastapi import APIRouter, Query

from networkgraph.database import get_db
from networkgraph.routers.utils import (
    _norm_nid, _get_filtered_narratives, _threshold_counts, 
    _edge_width, NODE_COLORS, EDGE_COLORS, MAX_DOMAINS_PER_SUB, MAX_AUTHORS_PER_SUB
)

log = logging.getLogger("sntis.graph")
router = APIRouter()

@router.get("/spread-levels")
def get_spread_levels():
    with get_db() as con:
        return _threshold_counts(
            con,
            table="narratives",
            column="unique_authors",
            base_levels=[1, 2, 3, 4, 5, 6, 10],
        )

@router.get("/timeline")
def get_timeline(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    with get_db() as con:
        # User Fix: Use daily_volume table instead of scanning posts
        where = []
        params = []
        if start_date:
            where.append("created_datetime::DATE >= ?::DATE")
            params.append(start_date)
        if end_date:
            where.append("created_datetime::DATE <= ?::DATE")
            params.append(end_date)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""

        # Timeline for narratives still needs subreddit_edges grouping
        rows = con.execute(
            f"""
            SELECT
                created_datetime::DATE AS date,
                narrative_id,
                COUNT(*) AS post_count
            FROM subreddit_edges
            {where_sql}
            GROUP BY 1, 2
            ORDER BY 1, 2
            LIMIT 5000
            """,
            params,
        ).fetchall()

        # User Fix: Use daily_volume for total counts
        date_totals = con.execute(
            f"""
            SELECT created_datetime::DATE AS date, post_count
            FROM daily_volume
            {where_sql}
            ORDER BY 1
            """,
            params,
        ).fetchall()

        return {
            "timeline": [
                {"date": str(r[0]), "narrative_id": str(r[1]), "post_count": int(r[2])}
                for r in rows
            ],
            "date_totals": [{"date": str(r[0]), "post_count": int(r[1])} for r in date_totals],
        }

@router.get("/graph")
def get_intelligence_graph(
    mode: Annotated[str, Query(pattern="^(spread|sources|amplifiers|all)$")] = "all",
    min_authors: Annotated[int, Query(ge=0)] = 1,
    min_subreddits: Annotated[int, Query(ge=0)] = 0,
    progressive: Annotated[bool, Query()] = False,
    top_n: Annotated[int, Query(ge=5, le=80)] = 14,
    start_date: Annotated[Optional[str], Query()] = None,
    end_date: Annotated[Optional[str], Query()] = None,
    narrative_id: Annotated[Optional[str], Query(description="If set, restrict graph to a single narrative_id")] = None,
    author: Annotated[Optional[str], Query(description="If set, restrict graph to narratives containing this author")] = None,
):
    with get_db() as con:
        ndf = _get_filtered_narratives(con, min_authors, min_subreddits, start_date, end_date)
        if ndf.empty:
            return {"nodes": [], "edges": []}

        narrative_ids = {_norm_nid(v) for v in ndf["narrative_id"].astype(str).tolist()}

        # Optional filter: narrative_id
        if narrative_id:
            nid = _norm_nid(narrative_id)
            narrative_ids = {nid} if nid in narrative_ids else set()

        # Optional filter: author (keep only narratives where this author appears in subreddit_edges)
        if author and narrative_ids:
            author_val = str(author).strip()
            if author_val:
                # Apply date filtering if present (matches other endpoints)
                where = ["author = ?", "author IS NOT NULL", "author <> ''"]
                params: list = [author_val]
                if start_date:
                    where.append("created_datetime::DATE >= ?::DATE")
                    params.append(start_date)
                if end_date:
                    where.append("created_datetime::DATE <= ?::DATE")
                    params.append(end_date)

                where_sql = f"WHERE {' AND '.join(where)}"
                rows = con.execute(
                    f"""
                    SELECT DISTINCT narrative_id
                    FROM subreddit_edges
                    {where_sql}
                    """,
                    params,
                ).fetchall()
                author_nids = {_norm_nid(r[0]) for r in rows if r and r[0] is not None}
                narrative_ids = narrative_ids.intersection(author_nids)

        if not narrative_ids:
            return {"nodes": [], "edges": []}

        narrative_ids_sql = "', '".join([v.replace("'", "''") for v in narrative_ids])

        nodes = []
        edges = []
        node_dict = {} # Performance: Dictionary for deduplication
        
        def add_node(node):
            if node["id"] not in node_dict:
                node_dict[node["id"]] = node
                nodes.append(node)
                
        if mode in ("spread", "all"):
            # User Optimization: Single query for edges, avoid infinite scanning
            query = f"""
                SELECT 
                    origin_subreddit AS source, 
                    subreddit AS target, 
                    COUNT(*) as weight
                FROM subreddit_edges
                WHERE narrative_id IN ('{narrative_ids_sql}')
                  AND origin_subreddit IS NOT NULL
                  AND origin_subreddit <> subreddit
                GROUP BY origin_subreddit, subreddit
                LIMIT 300
            """
            edge_rows = con.execute(query).fetchall()

            out_degree = defaultdict(int)
            in_degree = defaultdict(int)
            temp_edges = []
            
            for src, tgt, weight in edge_rows:
                src_str, tgt_str, w_int = str(src), str(tgt), int(weight)
                eid = hashlib.md5(f"ss::{src_str}::{tgt_str}".encode()).hexdigest()[:12]
                temp_edges.append(
                    {
                        "id": eid,
                        "from": f"sub::{src_str}",
                        "to": f"sub::{tgt_str}",
                        "edge_type": "spread",
                        "color": {"color": EDGE_COLORS["spread"], "opacity": 0.35},
                        "width": _edge_width(w_int),
                        "title": f"{src_str} -> {tgt_str} ({w_int})",
                        "arrows": "to",
                        "source_name": src_str,
                        "target_name": tgt_str
                    }
                )
                out_degree[src_str] += 1
                in_degree[tgt_str] += 1

            subreddits = set([r[0] for r in edge_rows] + [r[1] for r in edge_rows])

            if progressive and subreddits:
                ranked = sorted(
                    list(subreddits),
                    key=lambda s: (out_degree.get(s, 0) + in_degree.get(s, 0), out_degree.get(s, 0)),
                    reverse=True,
                )
                keep = set(ranked[:top_n])
                edges = [
                    {k: v for k, v in e.items() if k not in ["source_name", "target_name"]}
                    for e in temp_edges
                    if e["source_name"] in keep and e["target_name"] in keep
                ]
                subreddits = keep
            else:
                edges = [
                    {k: v for k, v in e.items() if k not in ["source_name", "target_name"]}
                    for e in temp_edges
                ]

            for sub in subreddits:
                size = max(18, min(56, 20 + out_degree[sub] * 3))
                add_node(
                    {
                        "id": f"sub::{sub}",
                        "label": sub,
                        "type": "subreddit",
                        "shape": "dot",
                        "size": size,
                        "color": NODE_COLORS["subreddit"],
                        "font": {"color": "#ffffff", "size": 12},
                    }
                )

        if mode in ("sources", "all"):
            # SQL Optimization: Use subreddit_edges directly for sources linking subreddits to domains
            rows = con.execute(
                f"""
                SELECT subreddit, domain, COUNT(*) as cnt
                FROM subreddit_edges
                WHERE narrative_id IN ('{narrative_ids_sql}')
                  AND domain IS NOT NULL AND domain <> ''
                GROUP BY 1, 2
                ORDER BY cnt DESC
                LIMIT 1000
                """
            ).fetchall()

            per_sub = defaultdict(list)
            dom_urls = {}
            dom_freq = defaultdict(int)
            
            for sub, dom, cnt in rows:
                per_sub[str(sub)].append((str(dom), int(cnt)))
                if str(dom) not in dom_urls or not dom_urls[str(dom)]:
                    dom_urls[str(dom)] = None

            for sub, pairs in per_sub.items():
                sub_str = str(sub)
                add_node({
                    "id": f"sub::{sub_str}",
                    "label": sub_str,
                    "type": "subreddit",
                    "shape": "dot",
                    "size": 22.0,
                    "color": NODE_COLORS["subreddit"],
                    "font": {"color": "#ffffff", "size": 12},
                })

                for dom_raw, cnt_raw in sorted(pairs, key=lambda x: x[1], reverse=True)[:MAX_DOMAINS_PER_SUB]:
                    dom_str, c_int = str(dom_raw), int(cnt_raw)
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

            for dom, freq in dom_freq.items():
                size = max(24, min(54, 24 + int(freq ** 0.45)))
                add_node(
                    {
                        "id": f"dom::{dom}",
                        "label": dom,
                        "type": "domain",
                        "shape": "triangle",
                        "size": size,
                        "color": NODE_COLORS["domain"],
                        "font": {"color": "#ffffff", "size": 11, "background": "rgba(0,0,0,0.6)"},
                        "metadata": {"url": dom_urls.get(dom)},
                    }
                )

        if mode in ("amplifiers", "all"):
            amp_rows = con.execute("SELECT author, total_relative_amplification FROM amplification").fetchall()
            amp_map = {str(a): float(s or 0.0) for a, s in amp_rows}

            # SQL Optimization: Use subreddit_edges directly for amplifiers linking authors to subreddits
            rows = con.execute(
                f"""
                SELECT author, subreddit, COUNT(*) as cnt
                FROM subreddit_edges
                WHERE narrative_id IN ('{narrative_ids_sql}')
                  AND author IS NOT NULL AND author <> ''
                GROUP BY 1, 2
                ORDER BY cnt DESC
                LIMIT 1000
                """
            ).fetchall()

            per_sub = defaultdict(list)
            for author, sub, cnt in rows:
                per_sub[str(sub)].append((str(author), int(cnt)))

            for sub, pairs in per_sub.items():
                sub_str = str(sub)
                add_node({
                    "id": f"sub::{sub_str}",
                    "label": sub_str,
                    "type": "subreddit",
                    "shape": "dot",
                    "size": 22.0,
                    "color": NODE_COLORS["subreddit"],
                    "font": {"color": "#ffffff", "size": 12},
                })
                
                top_pairs = sorted(pairs, key=lambda x: x[1], reverse=True)[:MAX_AUTHORS_PER_SUB]
                for author_raw, cnt_raw in top_pairs:
                    auth_str, cnt_int = str(author_raw), int(cnt_raw)
                    amp_score = float(amp_map.get(auth_str, 0.0))

                    eid = hashlib.md5(f"as::{auth_str}::{sub}".encode()).hexdigest()[:12]
                    edges.append(
                        {
                            "id": eid,
                            "from": f"aut::{auth_str}",
                            "to": f"sub::{sub}",
                            "edge_type": "amplifier",
                            "color": {"color": EDGE_COLORS["amplifier"], "opacity": 0.35},
                            "width": float(_edge_width(cnt_int)),
                            "title": f"u/{auth_str} -> r/{sub} ({cnt_int})",
                            "arrows": "to",
                        }
                    )

                    author_size = float(max(20, min(44, 20 + abs(amp_score) * 6)))
                    add_node(
                        {
                            "id": f"aut::{auth_str}",
                            "label": auth_str,
                            "type": "author",
                            "shape": "square",
                            "size": author_size,
                            "color": NODE_COLORS["author"],
                            "font": {"color": "#ffffff", "size": 10, "background": "rgba(0,0,0,0.6)"},
                        }
                    )

        # SQL Fix: Use subreddit_edges for keyword stats (no posts.cluster_id)
        stats_query = f"""
            SELECT title, domain
            FROM subreddit_edges
            WHERE narrative_id IN ('{narrative_ids_sql}')
            LIMIT 1000
        """
        rows = con.execute(stats_query).fetchall()
        
        words = []
        stop_words = {'a', 'the', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'with', 'from', 'by', 'of', 'is', 'are', 'was', 'were', 'that', 'this', 'it', 'its', 'as', 'but', 'not'} # Basic set
        from collections import Counter
        
        dom_freq = defaultdict(int)
        for t, d in rows:
            if t:
                for w in t.lower().split():
                    w_clean = "".join(filter(str.isalnum, w))
                    if len(w_clean) > 3 and w_clean not in stop_words:
                        words.append(w_clean)
            if d:
                dom_freq[str(d)] += 1
        
        top_words = Counter(words).most_common(10)
        keyword_stats = [{"keyword": w, "count": c} for w, c in top_words]
        top_sources = sorted([{"domain": d, "count": f} for d, f in dom_freq.items()], key=lambda x: x["count"], reverse=True)[:10]

        return {"nodes": nodes, "edges": edges, "keyword_stats": keyword_stats, "top_sources": top_sources}
