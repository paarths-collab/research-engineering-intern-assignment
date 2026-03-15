"""
hybrid_chatbot/sql_engine.py
---------------------------
DuckDB-backed SQL engine with lightweight NL-to-SQL translation.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
import calendar
from pathlib import Path
from typing import Optional, Tuple

import duckdb
import pandas as pd

from .config import DATA_DIR, DUCKDB_PATH, CSV_TABLES, REBUILD_SQL

logger = logging.getLogger("hybrid_chatbot.sql")


@dataclass
class SQLPlan:
    sql: str
    description: str
    tables: list[str]


class SQLStore:
    def __init__(self, db_path: Path = DUCKDB_PATH):
        self.db_path = db_path
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._valid_subreddits: set[str] | None = None
        self._max_date: Optional[date] = None

    def connect(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect(str(self.db_path), read_only=False)
        return self._conn

    def initialize(self) -> None:
        conn = self.connect()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        for csv_file, table in CSV_TABLES.items():
            csv_path = DATA_DIR / csv_file
            if not csv_path.exists():
                logger.warning("Missing CSV for table %s: %s", table, csv_path)
                continue
            if (not REBUILD_SQL) and self._table_exists(conn, table):
                continue
            logger.info("Loading %s into %s", csv_file, table)
            conn.execute(
                f"CREATE OR REPLACE TABLE {table} AS "
                f"SELECT * FROM read_csv_auto('{csv_path.as_posix()}', header=True)"
            )

    def _table_exists(self, conn: duckdb.DuckDBPyConnection, table: str) -> bool:
        try:
            res = conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
                [table],
            ).fetchone()
            return bool(res and res[0] > 0)
        except Exception:
            return False

    def execute(self, sql: str) -> pd.DataFrame:
        conn = self.connect()
        return conn.execute(sql).df()

    def valid_subreddits(self) -> set[str]:
        if self._valid_subreddits is not None:
            return self._valid_subreddits
        try:
            df = self.execute("SELECT DISTINCT subreddit FROM subreddit_domain_flow_v2")
            self._valid_subreddits = {str(s) for s in df["subreddit"].dropna().tolist()}
        except Exception:
            self._valid_subreddits = set()
        return self._valid_subreddits

    def dataset_max_date(self) -> Optional[date]:
        if self._max_date is not None:
            return self._max_date
        for table in ("graph_edge_intelligence_table", "clean_posts"):
            try:
                df = self.execute(
                    f"SELECT MAX(CAST(created_datetime AS DATE)) AS max_date FROM {table}"
                )
                if not df.empty and pd.notna(df.iloc[0]["max_date"]):
                    self._max_date = df.iloc[0]["max_date"]
                    return self._max_date
            except Exception:
                continue
        return None


class SQLTranslator:
    def __init__(self, valid_subreddits: set[str]):
        self.valid_subreddits = valid_subreddits

    def build_plan(self, query: str, reference_date: Optional[date] = None) -> Optional[SQLPlan]:
        q = query.lower().strip()
        narrative_token = _extract_narrative_token(query)
        subreddit = _extract_subreddit(query, self.valid_subreddits)
        date_range = _extract_date_range(query, reference_date)

        # Spike detection (for hybrid queries)
        if _has_any(q, ["spike", "spiked", "surge", "jump"]) and narrative_token:
            narrative_like = _narrative_like(narrative_token)
            date_filter = _date_filter("created_datetime", date_range)
            sql = (
                "SELECT CAST(created_datetime AS DATE) AS date, COUNT(*) AS post_count "
                "FROM graph_edge_intelligence_table "
                f"WHERE narrative_id ILIKE '{_escape(narrative_like)}' {date_filter} "
                "GROUP BY date "
                "ORDER BY post_count DESC "
                "LIMIT 1"
            )
            return SQLPlan(sql=sql, description="Narrative spike date", tables=["graph_edge_intelligence_table"])
        if _has_any(q, ["spike", "spiked", "surge", "jump"]) and not narrative_token:
            date_filter = _date_filter("created_datetime", date_range)
            sql = (
                "SELECT CAST(created_datetime AS DATE) AS date, post_count "
                "FROM daily_volume_v2 "
                f"WHERE 1=1 {date_filter} "
                "ORDER BY post_count DESC "
                "LIMIT 1"
            )
            return SQLPlan(sql=sql, description="Overall spike date", tables=["daily_volume_v2"])

        # Domain frequency
        if _has_any(q, ["domain", "domains"]) and _has_any(q, ["top", "most", "frequent", "frequently"]):
            where = ""
            if subreddit:
                where = f"WHERE subreddit = '{_escape(subreddit)}'"
            sql = (
                "SELECT domain, SUM(count) AS total_count "
                "FROM subreddit_domain_flow_v2 "
                f"{where} "
                "GROUP BY domain "
                "ORDER BY total_count DESC "
                "LIMIT 10"
            )
            return SQLPlan(sql=sql, description="Top domains by frequency", tables=["subreddit_domain_flow_v2"])

        # Echo chamber score
        if _has_any(q, ["echo chamber", "echo-chamber", "echo"]) and _has_any(q, ["highest", "top", "most"]):
            sql = (
                "SELECT subreddit, lift "
                "FROM echo_chamber_scores "
                "ORDER BY lift DESC "
                "LIMIT 1"
            )
            return SQLPlan(sql=sql, description="Highest echo chamber score", tables=["echo_chamber_scores"])
        if _has_any(q, ["echo chamber", "echo-chamber", "echo"]):
            sql = (
                "SELECT subreddit, lift "
                "FROM echo_chamber_scores "
                "ORDER BY lift DESC "
                "LIMIT 10"
            )
            return SQLPlan(sql=sql, description="Echo chamber scores", tables=["echo_chamber_scores"])

        # Dominant narratives in a subreddit
        if _has_any(q, ["narrative", "narratives"]) and subreddit and _has_any(q, ["dominant", "main", "top", "most"]):
            sql = (
                "SELECT nr.representative_title, nr.primary_domain, COUNT(*) AS post_count "
                "FROM narrative_diffusion_table nd "
                "JOIN narrative_registry nr ON nd.narrative_id = nr.narrative_id "
                f"WHERE nd.subreddit = '{_escape(subreddit)}' "
                "GROUP BY nr.representative_title, nr.primary_domain "
                "ORDER BY post_count DESC "
                "LIMIT 10"
            )
            return SQLPlan(sql=sql, description="Dominant narratives by subreddit", tables=["narrative_diffusion_table", "narrative_registry"])

        # Subreddit amplification for a narrative
        if _has_any(q, ["subreddit", "subreddits"]) and narrative_token and _has_any(q, ["most", "top", "amplified", "amplify"]):
            narrative_like = _narrative_like(narrative_token)
            sql = (
                "SELECT subreddit, COUNT(*) AS post_count "
                "FROM narrative_diffusion_table "
                f"WHERE narrative_id ILIKE '{_escape(narrative_like)}' "
                "GROUP BY subreddit "
                "ORDER BY post_count DESC "
                "LIMIT 10"
            )
            return SQLPlan(sql=sql, description="Subreddit amplification for narrative", tables=["narrative_diffusion_table"])

        # Narrative volume (highest)
        if _has_any(q, ["highest", "most", "top"]) and _has_any(q, ["narrative", "volume"]):
            date_filter = _date_filter("created_datetime", date_range)
            sql = (
                "SELECT narrative_id, COUNT(*) AS post_count "
                "FROM graph_edge_intelligence_table "
                f"WHERE 1=1 {date_filter} "
                "GROUP BY narrative_id "
                "ORDER BY post_count DESC "
                "LIMIT 1"
            )
            return SQLPlan(sql=sql, description="Highest narrative volume", tables=["graph_edge_intelligence_table"])

        # Trend over time
        if _has_any(q, ["trend", "over time", "time series"]):
            if narrative_token:
                narrative_like = _narrative_like(narrative_token)
                date_filter = _date_filter("created_datetime", date_range)
                sql = (
                    "SELECT CAST(created_datetime AS DATE) AS date, COUNT(*) AS post_count "
                    "FROM graph_edge_intelligence_table "
                    f"WHERE narrative_id ILIKE '{_escape(narrative_like)}' {date_filter} "
                    "GROUP BY date "
                    "ORDER BY date"
                )
                return SQLPlan(sql=sql, description="Narrative trend over time", tables=["graph_edge_intelligence_table"])

            date_filter = _date_filter("created_datetime", date_range)
            sql = (
                "SELECT CAST(created_datetime AS DATE) AS date, post_count "
                "FROM daily_volume_v2 "
                f"WHERE 1=1 {date_filter} "
                "ORDER BY date"
            )
            return SQLPlan(sql=sql, description="Overall volume trend", tables=["daily_volume_v2"])

        # Generic post counts
        if _has_any(q, ["how many", "count", "number of"]) and _has_any(q, ["post", "posts"]):
            where_parts = []
            if subreddit:
                where_parts.append(f"subreddit = '{_escape(subreddit)}'")
            if date_range:
                dfilt = _date_filter("created_datetime", date_range)
                if dfilt.startswith("AND "):
                    dfilt = dfilt[4:]
                where_parts.append(dfilt)
            where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""
            sql = f"SELECT COUNT(*) AS post_count FROM clean_posts {where_clause}"
            return SQLPlan(sql=sql, description="Post count", tables=["clean_posts"])

        # Avg score by subreddit
        if _has_any(q, ["average score", "avg score", "average"]):
            if subreddit:
                sql = (
                    "SELECT subreddit, avg_score "
                    "FROM subreddit_intelligence_summary "
                    f"WHERE subreddit = '{_escape(subreddit)}'"
                )
            else:
                sql = "SELECT AVG(avg_score) AS avg_score FROM subreddit_intelligence_summary"
            return SQLPlan(sql=sql, description="Average score", tables=["subreddit_intelligence_summary"])

        return None


def parse_date_range(query: str, reference_date: Optional[date] = None) -> Optional[Tuple[str, str]]:
    """Public helper for extracting date ranges from user queries."""
    return _extract_date_range(query, reference_date)


# ── Helpers ─────────────────────────────────────────────────────────────────-

def _has_any(text: str, needles: list[str]) -> bool:
    return any(n in text for n in needles)


def _escape(value: str) -> str:
    return value.replace("'", "''")


def _extract_narrative_token(query: str) -> Optional[str]:
    m = re.search(r"\bnarrative\s+([A-Za-z0-9_.-]+)", query, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"\bN(\d+)\b", query, re.IGNORECASE)
    if m:
        return f"N{m.group(1)}"
    return None


def _narrative_like(token: str) -> str:
    token = token.strip()
    if token.upper().startswith("N") and token[1:].isdigit():
        return f"{int(token[1:])}.%"
    if token.isdigit():
        return f"{int(token)}.%"
    if "%" in token:
        return token
    return f"%{token}%"


def _extract_subreddit(query: str, valid_subreddits: set[str]) -> Optional[str]:
    m = re.search(r"r/([A-Za-z0-9_]+)", query)
    if m:
        return m.group(1)
    q = query.lower()
    for sub in valid_subreddits:
        if sub.lower() in q:
            return sub
    return None


def _extract_date_range(query: str, reference_date: Optional[date]) -> Optional[Tuple[str, str]]:
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", query)
    if len(dates) >= 2:
        return dates[0], dates[1]
    today = reference_date or date.today()
    q = query.lower()

    # Month name ranges (e.g., "late January 2025", "Jan 2025")
    month_range = _parse_named_month_range(q, reference_date)
    if month_range:
        return month_range

    if "yesterday" in q:
        d = today - timedelta(days=1)
        return d.isoformat(), d.isoformat()
    if "today" in q:
        return today.isoformat(), today.isoformat()
    if "last week" in q or "past week" in q:
        return (today - timedelta(days=7)).isoformat(), today.isoformat()
    if "last month" in q or "past month" in q:
        return (today - timedelta(days=30)).isoformat(), today.isoformat()
    if "last year" in q or "past year" in q:
        return (today - timedelta(days=365)).isoformat(), today.isoformat()
    m = re.search(r"past (\d+) days", q)
    if m:
        days = int(m.group(1))
        return (today - timedelta(days=days)).isoformat(), today.isoformat()
    return None


def _parse_named_month_range(query: str, reference_date: Optional[date]) -> Optional[Tuple[str, str]]:
    month_map = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }

    # with year (e.g., "late January 2025")
    m = re.search(
        r"\b(early|mid|late)?\s*(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
        r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|"
        r"nov(?:ember)?|dec(?:ember)?)\s+(20\d{2})\b",
        query,
    )
    if m:
        qualifier = (m.group(1) or "").strip()
        month_token = m.group(2)
        year = int(m.group(3))
        month = month_map[month_token[:3]]
        return _qualified_month_range(year, month, qualifier)

    # without year (fall back to reference_date year if available)
    m = re.search(
        r"\b(early|mid|late)?\s*(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
        r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|"
        r"nov(?:ember)?|dec(?:ember)?)\b",
        query,
    )
    if m:
        qualifier = (m.group(1) or "").strip()
        month_token = m.group(2)
        year = reference_date.year if reference_date else date.today().year
        month = month_map[month_token[:3]]
        return _qualified_month_range(year, month, qualifier)

    return None


def _qualified_month_range(year: int, month: int, qualifier: str) -> Tuple[str, str]:
    last_day = calendar.monthrange(year, month)[1]
    if qualifier == "early":
        start, end = 1, min(10, last_day)
    elif qualifier == "mid":
        start, end = 11, min(20, last_day)
    elif qualifier == "late":
        start, end = 21, last_day
    else:
        start, end = 1, last_day
    return (
        f"{year:04d}-{month:02d}-{start:02d}",
        f"{year:04d}-{month:02d}-{end:02d}",
    )


def _date_filter(column: str, date_range: Optional[Tuple[str, str]]) -> str:
    if not date_range:
        return ""
    start, end = date_range
    return f"AND CAST({column} AS DATE) BETWEEN '{_escape(start)}' AND '{_escape(end)}'"
