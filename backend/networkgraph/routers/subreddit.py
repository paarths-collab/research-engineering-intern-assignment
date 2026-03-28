import math
import hashlib
import logging
from collections import defaultdict
from typing import Annotated
from fastapi import APIRouter, Query

from networkgraph.database import get_db
from networkgraph.routers.utils import (
    _norm_nid, _parse_sequence, _get_filtered_narratives, _threshold_counts, _edge_width,
    NODE_COLORS, EDGE_COLORS, MAX_DOMAINS_PER_SUB, MAX_AUTHORS_PER_SUB
)

log = logging.getLogger("sntis.subreddit")
router = APIRouter()

@router.get("/subreddit-reach")
def get_subreddit_reach():
    with get_db() as con:
        return _threshold_counts(
            con,
            table="narratives",
            column="unique_subreddits_x",
            base_levels=[1, 2, 3, 4, 5, 6],
        )

@router.get("/subreddit/neighbors")
def get_subreddit_neighbors(
    name: Annotated[str, Query(min_length=1)],
    min_authors: Annotated[int, Query(ge=0)] = 1,
    min_subreddits: Annotated[int, Query(ge=0)] = 0,
    depth: Annotated[int, Query(ge=1, le=2)] = 1,
):
    with get_db() as con:
        subreddit = str(name).strip()
        ndf = _get_filtered_narratives(con, min_authors, min_subreddits, None, None)
        if ndf.empty:
            return {"name": subreddit, "nodes": [], "edges": []}

        cluster_ids: list[int] = []
        for raw in ndf["cluster_id"].tolist():
            try:
                cluster_ids.append(int(raw))
            except (TypeError, ValueError):
                continue

        if not cluster_ids:
            return {"name": subreddit, "nodes": [], "edges": []}

        cid_sql = ",".join(str(cid) for cid in sorted(set(cluster_ids)))

        # SQL Fix: Use subreddit_edges instead of posts (which lacks cluster_id)
        narrative_rows = con.execute(
            f"""
            SELECT DISTINCT narrative_id
            FROM subreddit_edges
            WHERE cluster_id IN ({cid_sql})
              AND subreddit = ?
            """,
            [subreddit],
        ).fetchall()
        
        narrative_ids = [_norm_nid(r[0]) for r in narrative_rows if r and r[0] is not None]
        if not narrative_ids:
            return {"name": subreddit, "nodes": [], "edges": []}

        narrative_ids_sql = "', '".join([v.replace("'", "''") for v in set(narrative_ids)])

        nodes = []
        edges = []
        node_ids = set()

        def add_node(node):
            nid = node["id"]
            if nid not in node_ids:
                node_ids.add(nid)
                nodes.append(node)

        seq_rows = con.execute(
            f"""
            SELECT spread_sequence
            FROM chains
            WHERE narrative_id IN ('{narrative_ids_sql}')
            """
        ).fetchall()
        
        all_pair_weight = defaultdict(int)
        for (spread_sequence,) in seq_rows:
            seq = _parse_sequence(spread_sequence)
            for i in range(len(seq) - 1):
                src = seq[i].strip()
                tgt = seq[i + 1].strip()
                if src and tgt and src != tgt:
                    all_pair_weight[(src, tgt)] += 1

        first_hop_subs = set()
        for (src, tgt), _weight in all_pair_weight.items():
            if src == subreddit:
                first_hop_subs.add(tgt)
            if tgt == subreddit:
                first_hop_subs.add(src)

        allowed_subs = {subreddit}
        if depth >= 2:
            allowed_subs.update(first_hop_subs)

        pair_weight = defaultdict(int)
        for (src, tgt), weight in all_pair_weight.items():
            if depth == 1:
                if src == subreddit or tgt == subreddit:
                    pair_weight[(src, tgt)] += weight
            else:
                if src in allowed_subs or tgt in allowed_subs:
                    pair_weight[(src, tgt)] += weight

        for (src, tgt), weight in pair_weight.items():
            src_str, tgt_str, w_int = str(src), str(tgt), int(weight)
            edges.append(
                {
                    "id": hashlib.md5(f"nei-ss::{src_str}::{tgt_str}".encode()).hexdigest()[:12],
                    "from": f"sub::{src_str}",
                    "to": f"sub::{tgt_str}",
                    "edge_type": "spread",
                    "color": {"color": EDGE_COLORS["spread"], "opacity": 0.35},
                    "width": float(_edge_width(w_int)),
                    "title": f"r/{src_str} -> r/{tgt_str} ({w_int})",
                    "arrows": "to",
                }
            )

        scope_subs = sorted(allowed_subs)
        scope_subs_sql = "', '".join([s.replace("'", "''") for s in scope_subs])
        
        # SQL Fix: Use subreddit_edges for domain links
        dom_rows = con.execute(
            f"""
            SELECT subreddit, domain, COUNT(*) AS cnt
            FROM subreddit_edges
            WHERE narrative_id IN ('{narrative_ids_sql}')
              AND subreddit IN ('{scope_subs_sql}')
              AND domain IS NOT NULL AND domain <> ''
            GROUP BY 1, 2
            ORDER BY cnt DESC
            LIMIT 80
            """
        ).fetchall()
        
        for sub, dom, cnt in dom_rows:
            sub = str(sub)
            dom = str(dom)
            cnt = int(cnt)
            edges.append(
                {
                    "id": hashlib.md5(f"nei-sd::{sub}::{dom}".encode()).hexdigest()[:12],
                    "from": f"sub::{sub}",
                    "to": f"dom::{dom}",
                    "edge_type": "source",
                    "color": {"color": EDGE_COLORS["source"], "opacity": 0.35},
                    "width": _edge_width(cnt),
                    "title": f"{sub} -> {dom} ({cnt})",
                    "arrows": "to",
                }
            )
            add_node(
                {
                    "id": f"dom::{dom}",
                    "label": dom,
                    "type": "domain",
                    "shape": "triangle",
                    "size": max(16, min(42, 16 + int(math.log(cnt + 1) * 6))),
                    "color": NODE_COLORS["domain"],
                    "font": {"color": "#ffffff", "size": 10},
                }
            )

        # SQL Fix: Use subreddit_edges for author links
        aut_rows = con.execute(
            f"""
            SELECT author, subreddit, COUNT(*) AS cnt
            FROM subreddit_edges
            WHERE narrative_id IN ('{narrative_ids_sql}')
              AND subreddit IN ('{scope_subs_sql}')
              AND author IS NOT NULL AND author <> ''
            GROUP BY 1, 2
            ORDER BY cnt DESC
            LIMIT 120
            """
        ).fetchall()
        
        for author, sub, cnt in aut_rows:
            author = str(author)
            sub = str(sub)
            cnt = int(cnt)
            edges.append(
                {
                    "id": hashlib.md5(f"nei-as::{author}::{sub}".encode()).hexdigest()[:12],
                    "from": f"aut::{author}",
                    "to": f"sub::{sub}",
                    "edge_type": "amplifier",
                    "color": {"color": EDGE_COLORS["amplifier"], "opacity": 0.35},
                    "width": _edge_width(cnt),
                    "title": f"{author} -> {sub} ({cnt})",
                    "arrows": "to",
                }
            )
            add_node(
                {
                    "id": f"aut::{author}",
                    "label": author,
                    "type": "author",
                    "shape": "square",
                    "size": max(11, min(30, 11 + int(math.log(cnt + 1) * 5))),
                    "color": NODE_COLORS["author"],
                    "font": {"color": "#ffffff", "size": 10},
                }
            )

        subreddits = {subreddit}
        for src, tgt in pair_weight.keys():
            subreddits.add(str(src))
            subreddits.add(str(tgt))

        for sub in subreddits:
            is_focus = sub == subreddit
            add_node(
                {
                    "id": f"sub::{sub}",
                    "label": sub,
                    "type": "subreddit",
                    "shape": "dot",
                    "size": 34 if is_focus else 22,
                    "color": {
                        "background": "#22C55E" if is_focus else NODE_COLORS["subreddit"]["background"],
                        "border": "#166534" if is_focus else NODE_COLORS["subreddit"]["border"],
                    },
                    "font": {"color": "#ffffff", "size": 13 if is_focus else 12},
                }
            )

        return {"name": subreddit, "depth": depth, "nodes": nodes, "edges": edges}

@router.get("/subreddit/{subreddit}/details")
def get_subreddit_details(
    subreddit: str,
    min_authors: Annotated[int, Query(ge=0)] = 1,
    min_subreddits: Annotated[int, Query(ge=0)] = 0,
):
    with get_db() as con:
        ndf = _get_filtered_narratives(con, min_authors, min_subreddits, None, None)
        if ndf.empty:
            return {
                "subreddit": subreddit,
                "summary": {"total_posts": 0, "distinct_authors": 0, "distinct_domains": 0, "narratives": 0, "first_seen": None, "last_seen": None},
                "top_domains": [], "top_authors": [], "connected_subreddits": [], "top_narratives": [],
            }

        cluster_ids: list[int] = []
        for raw in ndf["cluster_id"].tolist():
            try: cluster_ids.append(int(raw))
            except (TypeError, ValueError): continue

        if not cluster_ids:
            return {
                "subreddit": subreddit,
                "summary": {"total_posts": 0, "distinct_authors": 0, "distinct_domains": 0, "narratives": 0, "first_seen": None, "last_seen": None},
                "top_domains": [], "top_authors": [], "connected_subreddits": [], "top_narratives": [],
            }

        cid_sql = ",".join(str(cid) for cid in sorted(set(cluster_ids)))

        # SQL Fix: Use subreddit_edges instead of posts (which lacks cluster_id)
        summary = con.execute(
            f"""
            SELECT
                COUNT(*) AS total_posts,
                COUNT(DISTINCT author) AS distinct_authors,
                COUNT(DISTINCT domain) AS distinct_domains,
                COUNT(DISTINCT cluster_id) AS narratives,
                MIN(created_datetime) AS first_seen,
                MAX(created_datetime) AS last_seen
            FROM subreddit_edges
            WHERE cluster_id IN ({cid_sql})
              AND subreddit = ?
            """,
            [subreddit],
        ).fetchone()
        summary = summary or (0, 0, 0, 0, None, None)

        top_domains = con.execute(
            f"""
            SELECT domain, COUNT(*) AS cnt
            FROM subreddit_edges
            WHERE cluster_id IN ({cid_sql})
              AND subreddit = ?
              AND domain IS NOT NULL AND domain <> ''
            GROUP BY 1
            ORDER BY cnt DESC
            LIMIT 12
            """,
            [subreddit],
        ).fetchall()

        top_authors = con.execute(
            f"""
            SELECT author, COUNT(*) AS cnt
            FROM subreddit_edges
            WHERE cluster_id IN ({cid_sql})
              AND subreddit = ?
              AND author IS NOT NULL AND author <> ''
            GROUP BY 1
            ORDER BY cnt DESC
            LIMIT 12
            """,
            [subreddit],
        ).fetchall()

        connected_subs = con.execute(
            f"""
            SELECT s2.subreddit, COUNT(*) AS cnt
            FROM subreddit_edges s1
            JOIN subreddit_edges s2
              ON s1.cluster_id = s2.cluster_id
            WHERE s1.cluster_id IN ({cid_sql})
              AND s1.subreddit = ?
              AND s2.subreddit IS NOT NULL
              AND s2.subreddit <> ''
              AND s2.subreddit <> ?
            GROUP BY 1
            ORDER BY cnt DESC
            LIMIT 12
            """,
            [subreddit, subreddit],
        ).fetchall()

        top_narratives = con.execute(
            f"""
            SELECT n.narrative_id, n.representative_title, 1 AS cnt
            FROM narratives n
            JOIN chains c ON n.narrative_id = c.narrative_id
            WHERE c.spread_sequence LIKE '%' || ? || '%' 
            LIMIT 10
            """,
            [subreddit],
        ).fetchall()

        return {
            "subreddit": str(subreddit),
            "summary": {
                "total_posts": int(summary[0] or 0),
                "distinct_authors": int(summary[1] or 0),
                "distinct_domains": int(summary[2] or 0),
                "narratives": int(summary[3] or 0),
                "first_seen": str(summary[4]) if summary[4] else None,
                "last_seen": str(summary[5]) if summary[5] else None,
            },
            "top_domains": [{"domain": str(d), "count": int(c)} for d, c in top_domains],
            "top_authors": [{"author": str(a), "count": int(c)} for a, c in top_authors],
            "connected_subreddits": [{"subreddit": str(s), "count": int(c)} for s, c in connected_subs],
            "top_narratives": [{"narrative_id": str(nid), "title": str(title or ""), "count": int(c)} for nid, title, c in top_narratives],
        }

@router.get("/subreddit/{subreddit}/ecosystem")
def get_subreddit_ecosystem(
    subreddit: str,
    min_authors: Annotated[int, Query(ge=0)] = 1,
    min_subreddits: Annotated[int, Query(ge=0)] = 0,
):
    with get_db() as con:
        ndf = _get_filtered_narratives(con, min_authors, min_subreddits, None, None)
        if ndf.empty:
            return {"subreddit": subreddit, "nodes": [], "edges": []}

        cluster_ids: list[int] = []
        for raw in ndf["cluster_id"].tolist():
            try: cluster_ids.append(int(raw))
            except (TypeError, ValueError): continue

        if not cluster_ids:
            return {"subreddit": subreddit, "nodes": [], "edges": []}

        cid_sql = ",".join(str(cid) for cid in sorted(set(cluster_ids)))

        narrative_rows = con.execute(
            f"""
            SELECT DISTINCT n.narrative_id
            FROM narratives n
            JOIN chains c ON n.narrative_id = c.narrative_id
            WHERE n.cluster_id IN ({cid_sql})
              AND ? IN (
                SELECT trim(unnest(string_split(replace(replace(replace(c.spread_sequence, '[', ''), ']', ''), '''', ''), ', ')))
              )
            """,
            [subreddit],
        ).fetchall()

        narrative_ids = [_norm_nid(r[0]) for r in narrative_rows if r and r[0] is not None]
        if not narrative_ids:
            return {"subreddit": subreddit, "nodes": [], "edges": []}

        narrative_ids_sql = "', '".join([v.replace("'", "''") for v in set(narrative_ids)])

        nodes = []
        edges = []
        node_ids = set()

        def add_node(node):
            nid = node["id"]
            if nid not in node_ids:
                node_ids.add(nid)
                nodes.append(node)

        seq_rows = con.execute(
            f"""
            SELECT spread_sequence
            FROM chains
            WHERE narrative_id IN ('{narrative_ids_sql}')
            """
        ).fetchall()

        pair_weight = defaultdict(int)
        for (spread_sequence,) in seq_rows:
            seq = _parse_sequence(spread_sequence)
            for i in range(len(seq) - 1):
                src = seq[i].strip()
                tgt = seq[i + 1].strip()
                if src and tgt and src != tgt:
                    pair_weight[(src, tgt)] += 1

        for (src, tgt), weight in pair_weight.items():
            src_str, tgt_str, w_int = str(src), str(tgt), int(weight)
            edges.append(
                {
                    "id": hashlib.md5(f"eco-ss::{src_str}::{tgt_str}".encode()).hexdigest()[:12],
                    "from": f"sub::{src_str}",
                    "to": f"sub::{tgt_str}",
                    "edge_type": "spread",
                    "color": {"color": "#F43F5E", "opacity": 0.45},
                    "width": float(max(1.2, min(6.0, float(w_int) ** 0.45))),
                    "title": f"r/{src_str} -> r/{tgt_str} ({w_int})",
                    "arrows": "to",
                }
            )

        # Using subreddit_edges for consistency with the main graph
        src_rows = con.execute(
            f"""
            SELECT subreddit, domain, COUNT(*) AS cnt
            FROM subreddit_edges
            WHERE narrative_id IN ('{narrative_ids_sql}')
              AND domain IS NOT NULL AND domain <> ''
            GROUP BY 1, 2
            ORDER BY cnt DESC
            LIMIT 500
            """
        ).fetchall()

        per_sub_domains = defaultdict(list)
        for sub, dom, cnt in src_rows:
            per_sub_domains[str(sub)].append((str(dom), int(cnt)))

        for sub, pairs in per_sub_domains.items():
            sub_str = str(sub)
            for dom, cnt in sorted(pairs, key=lambda x: x[1], reverse=True)[:MAX_DOMAINS_PER_SUB]:
                dom_str, cnt_int = str(dom), int(cnt)
                edges.append(
                    {
                        "id": hashlib.md5(f"eco-sd::{sub_str}::{dom_str}".encode()).hexdigest()[:12],
                        "from": f"sub::{sub_str}",
                        "to": f"dom::{dom_str}",
                        "edge_type": "source",
                        "color": {"color": "#38BDF8", "opacity": 0.45},
                        "width": float(max(1.0, min(5.0, float(cnt_int) ** 0.35))),
                        "title": f"r/{sub_str} -> {dom_str} ({cnt_int})",
                        "arrows": "to",
                    }
                )
                add_node(
                    {
                        "id": f"dom::{dom_str}",
                        "label": dom_str,
                        "type": "domain",
                        "shape": "triangle",
                        "size": float(max(16, min(42, 16 + int(cnt_int ** 0.35)))),
                        "color": {"background": "#3B0A45", "border": "#E879F9"},
                        "font": {"color": "#ffffff", "size": 10},
                        "metadata": {"url": None},
                    }
                )

        # Using subreddit_edges for authors for much higher data quality
        amp_rows_raw = con.execute(
            f"""
            SELECT author, subreddit, COUNT(*) AS cnt
            FROM subreddit_edges
            WHERE narrative_id IN ('{narrative_ids_sql}')
              AND author IS NOT NULL AND author <> ''
            GROUP BY 1, 2
            ORDER BY cnt DESC
            LIMIT 500
            """
        ).fetchall()

        amp_scores_rows = con.execute("SELECT author, total_relative_amplification FROM amplification").fetchall()
        author_scores = {str(a): float(s or 0.0) for a, s in amp_scores_rows}

        per_sub_authors = defaultdict(list)
        for author, sub, cnt in amp_rows_raw:
            per_sub_authors[str(sub)].append((str(author), int(cnt)))

        for sub, pairs in per_sub_authors.items():
            sub_str = str(sub)
            for author, cnt in sorted(pairs, key=lambda x: x[1], reverse=True)[:MAX_AUTHORS_PER_SUB]:
                auth_str, cnt_int = str(author), int(cnt)
                edges.append(
                    {
                        "id": hashlib.md5(f"eco-as::{auth_str}::{sub_str}".encode()).hexdigest()[:12],
                        "from": f"aut::{auth_str}",
                        "to": f"sub::{sub_str}",
                        "edge_type": "amplifier",
                        "color": {"color": "#F59E0B", "opacity": 0.45},
                        "width": float(max(1.0, min(5.0, float(cnt_int) ** 0.35))),
                        "title": f"u/{auth_str} -> r/{sub_str} ({cnt_int})",
                        "arrows": "to",
                    }
                )
                amp_score = author_scores.get(auth_str, 0.0)
                author_size = float(max(11, min(44, 11 + abs(amp_score) * 4 + int(cnt_int ** 0.35))))
                add_node(
                    {
                        "id": f"aut::{auth_str}",
                        "label": auth_str,
                        "type": "author",
                        "shape": "square",
                        "size": author_size,
                        "color": {"background": "#3A2306", "border": "#FB923C"},
                        "font": {"color": "#ffffff", "size": 10},
                        "metadata": {"influence": amp_score},
                    }
                )

        subreddits = set()
        for e in edges:
            if str(e.get("from", "")).startswith("sub::"):
                subreddits.add(str(e["from"]).split("sub::", 1)[1])
            if str(e.get("to", "")).startswith("sub::"):
                subreddits.add(str(e["to"]).split("sub::", 1)[1])
        if subreddit: subreddits.add(subreddit)

        for sub in subreddits:
            is_focus = sub == subreddit
            add_node(
                {
                    "id": f"sub::{sub}",
                    "label": sub,
                    "type": "subreddit",
                    "shape": "dot",
                    "size": 34 if is_focus else 22,
                    "color": {
                        "background": "#0B2B3A" if not is_focus else "#1F2937",
                        "border": "#22D3EE" if not is_focus else "#FDE047",
                    },
                    "font": {"color": "#ffffff", "size": 12 if not is_focus else 13},
                }
            )

        return {"subreddit": subreddit, "nodes": nodes, "edges": edges}
