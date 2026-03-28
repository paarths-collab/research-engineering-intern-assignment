import logging
from typing import Optional, Annotated
from fastapi import APIRouter, Query

from networkgraph.database import get_db

log = logging.getLogger("sntis.leaderboard")
router = APIRouter()

@router.get("/leaderboard")
def get_leaderboard(
    limit: Annotated[int, Query(ge=1, le=200)] = 30,
    start_date: Annotated[Optional[str], Query()] = None,
    end_date: Annotated[Optional[str], Query()] = None,
):
    with get_db() as con:
        where = ["p.author IS NOT NULL", "p.author <> ''"]
        params: list = []
        if start_date:
            where.append("p.created_datetime::DATE >= ?::DATE")
            params.append(start_date)
        if end_date:
            where.append("p.created_datetime::DATE <= ?::DATE")
            params.append(end_date)

        where_sql = f"WHERE {' AND '.join(where)}"
        rows = con.execute(
            f"""
            SELECT
                p.author,
                COUNT(*) AS post_count,
                COUNT(DISTINCT p.subreddit) AS community_count,
                COALESCE(a.amplification_events, 0) AS amplification_score
            FROM posts p
            LEFT JOIN amplification a ON a.author = p.author
            {where_sql}
            GROUP BY p.author, a.amplification_events
            ORDER BY post_count DESC, amplification_score DESC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()

        return {
            "items": [
                {
                    "author": str(r[0]),
                    "post_count": int(r[1] or 0),
                    "community_count": int(r[2] or 0),
                    "amplification_score": float(r[3] or 0.0),
                }
                for r in rows
            ],
            "total": len(rows),
        }
