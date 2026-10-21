"""
hybrid_chatbot/sql_engine.py
---------------------------
DuckDB-backed SQL engine with lightweight NL-to-SQL translation.

Serving is always read-only for file-backed databases. Construction (CREATE from
the source CSVs) happens separately: in place when the destination is writable,
otherwise into a transient in-memory/temp-file database.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
import calendar
from pathlib import Path
from typing import Optional, Tuple

import duckdb
import pandas as pd

from .config import (
    CSV_TABLES,
    DATE_COLUMNS,
    REBUILD_SQL,
    TRANSIENT_MEMORY_MAX_BYTES,
    is_serverless,
    resolve_data_dir,
    resolve_db_path,
)

logger = logging.getLogger("hybrid_chatbot.sql")

STATE_UNINITIALIZED = "uninitialized"
STATE_READY = "ready"
STATE_DEGRADED = "degraded"
STATE_UNAVAILABLE = "unavailable"


@dataclass
class EntityFilter:
    """A user-supplied entity (subreddit / narrative) a plan filters on.

    Only ever bound as a query parameter; `table` and `column` are validated
    identifiers from the fixed templates.
    """

    label: str  # "subreddit" | "narrative"
    table: str
    column: str
    value: str
    match: str = "eq"  # "eq" (case-insensitive equality) | "like" (ILIKE pattern, escaped)
    display: Optional[str] = None  # what the user named, for messages (not the SQL pattern)


@dataclass
class SQLPlan:
    """A keyword-template query. `sql` holds `?` placeholders only; every value derived
    from the user's question is carried in `params` and bound by DuckDB."""

    sql: str
    description: str
    tables: list[str]
    date_range: Optional[Tuple[str, str]] = None
    params: list = field(default_factory=list)
    # count | ranking | series | aggregate
    kind: str = "ranking"
    # result columns that must be non-NULL and finite for a row to be a real value
    metrics: list[str] = field(default_factory=list)
    # (table, column) the date window filters on, to check the window against the data
    date_source: Optional[Tuple[str, str]] = None
    entities: list[EntityFilter] = field(default_factory=list)
    # caveats the answer must state (e.g. a time phrase that could not be applied)
    notes: list[str] = field(default_factory=list)


COVERAGE_FULL = "full"
COVERAGE_PARTIAL = "partial"
COVERAGE_NONE = "none"
COVERAGE_NOT_APPLICABLE = "not_applicable"


@dataclass
class Coverage:
    """Whether the dataset can speak to a plan's date window / entities at all.

    A count of 0 is only a genuine zero when coverage is `full`; with `none` there is
    simply no data for the question.
    """

    status: str = COVERAGE_NOT_APPLICABLE
    reason: Optional[str] = None
    window: Optional[dict] = None
    table_range: Optional[dict] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SQLStatus:
    state: str = STATE_UNINITIALIZED
    available_tables: list[str] = field(default_factory=list)
    missing_tables: list[str] = field(default_factory=list)
    error: Optional[str] = None
    # file (read-only persistent DB) | transient_memory | transient_file | none
    storage: str = "none"

    def to_dict(self) -> dict:
        return asdict(self)


class SQLUnavailableError(RuntimeError):
    """Raised when a query is attempted but no SQL database could be provided."""


# ── Construction helpers ─────────────────────────────────────────────────────

def _list_tables(conn: duckdb.DuckDBPyConnection) -> set[str]:
    try:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    except duckdb.Error:
        return set()
    return {str(r[0]) for r in rows}


def _lock_down(conn: duckdb.DuckDBPyConnection) -> None:
    """Defence in depth for the serving connection (the guard in `execute` is the
    primary control): no file/URL access and no further configuration changes. Only
    called once every table exists, so the CSV bootstrap (its own connections) is
    unaffected."""
    for statement in ("SET enable_external_access=false", "SET lock_configuration=true"):
        try:
            conn.execute(statement)
        except duckdb.Error as exc:
            logger.warning("Could not apply %s to the serving connection: %s", statement, exc)


def _sql_literal_path(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def populate_connection(
    conn: duckdb.DuckDBPyConnection,
    data_dir: Path,
    csv_tables: dict[str, str],
    force: bool = False,
) -> dict[str, int]:
    """Create any missing tables (all of them when force) from the CSVs.

    Returns {table: row_count} for every expected table present afterwards.
    I/O errors (read-only filesystem, ...) propagate so the caller can pick another
    destination; any other failure only skips that one table.
    """
    existing = _list_tables(conn)
    for csv_file, table in csv_tables.items():
        if table in existing and not force:
            continue
        csv_path = data_dir / csv_file
        if not csv_path.exists():
            logger.warning("Missing CSV for table %s: %s", table, csv_path)
            continue
        logger.info("Loading %s into %s", csv_file, table)
        try:
            conn.execute(
                f"CREATE OR REPLACE TABLE {table} AS "
                f"SELECT * FROM read_csv_auto('{_sql_literal_path(csv_path)}', header=True)"
            )
        except (OSError, duckdb.IOException):
            raise
        except duckdb.Error as exc:
            logger.warning("Could not load %s into %s: %s", csv_file, table, exc)
    present = _list_tables(conn)
    return {
        table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in csv_tables.values()
        if table in present
    }


def build_database(
    db_path: Path,
    data_dir: Path,
    csv_tables: dict[str, str] | None = None,
    force: bool = False,
) -> dict[str, int]:
    """Build (or complete) a DuckDB file from the CSVs with a read-write connection.

    A brand-new database is built under a temporary name and moved into place so a
    half-built file is never visible. The connection is closed before returning.
    """
    csv_tables = CSV_TABLES if csv_tables is None else csv_tables
    db_path = Path(db_path)
    data_dir = Path(data_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        conn = duckdb.connect(str(db_path), read_only=False)
        try:
            return populate_connection(conn, data_dir, csv_tables, force=force)
        finally:
            conn.close()

    tmp_path = db_path.with_name(f"{db_path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")
    try:
        conn = duckdb.connect(str(tmp_path), read_only=False)
        try:
            counts = populate_connection(conn, data_dir, csv_tables, force=force)
        finally:
            conn.close()
        if counts:
            os.replace(tmp_path, db_path)
        return counts
    finally:
        for leftover in (tmp_path, tmp_path.with_name(tmp_path.name + ".wal")):
            try:
                leftover.unlink()
            except OSError:
                pass


class SQLStore:
    def __init__(
        self,
        db_path: Path | str | None = None,
        data_dir: Path | str | None = None,
        csv_tables: dict[str, str] | None = None,
        rebuild: bool | None = None,
    ):
        self.db_path = Path(db_path) if db_path else resolve_db_path()
        self.data_dir = Path(data_dir) if data_dir else resolve_data_dir()
        self.csv_tables = dict(CSV_TABLES if csv_tables is None else csv_tables)
        self.rebuild = REBUILD_SQL if rebuild is None else rebuild
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._lock = threading.RLock()
        self._initialized = False
        self._status = SQLStatus()
        self._transient_dir: Path | None = None
        self._valid_subreddits: set[str] | None = None
        self._date_range: tuple[Optional[date], Optional[date]] | None = None
        self._max_date: Optional[date] = None

    # ── Lifecycle ────────────────────────────────────────────────────────────
    @property
    def status(self) -> SQLStatus:
        with self._lock:
            return SQLStatus(**asdict(self._status))

    def initialize(self) -> SQLStatus:
        """Idempotent, thread-safe. Never raises; the outcome is recorded in `status`."""
        with self._lock:
            if self._initialized:
                return self.status
            try:
                self._initialize_locked()
            except Exception as exc:  # noqa: BLE001 - recorded as an explicit status
                logger.exception("SQL initialization failed: %s", exc)
                self._close_conn()
                self._status = SQLStatus(
                    state=STATE_UNAVAILABLE,
                    available_tables=[],
                    missing_tables=list(self.csv_tables.values()),
                    error=f"SQL initialization failed: {exc}",
                    storage="none",
                )
            self._initialized = True
            self._valid_subreddits = None
            self._date_range = None
            self._max_date = None
            logger.info(
                "SQL store %s (storage=%s, missing=%s)",
                self._status.state, self._status.storage, self._status.missing_tables,
            )
            return self.status

    def connect(self) -> duckdb.DuckDBPyConnection:
        self.initialize()
        if self._conn is None:
            raise SQLUnavailableError(self._status.error or "SQL database unavailable")
        return self._conn

    def close(self) -> None:
        with self._lock:
            self._close_conn()
            if self._transient_dir is not None:
                shutil.rmtree(self._transient_dir, ignore_errors=True)
                self._transient_dir = None
            self._initialized = False
            self._status = SQLStatus()
            self._valid_subreddits = None
            self._date_range = None
            self._max_date = None

    def _close_conn(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass
            self._conn = None

    def _initialize_locked(self) -> None:
        expected = list(self.csv_tables.values())
        existing_conn, existing_tables = self._open_existing()
        missing = [t for t in expected if t not in existing_tables]

        if existing_conn is not None and not missing and not self.rebuild:
            # Complete prebuilt DB: serve it read-only, never issue a CREATE.
            self._serve(existing_conn, "file")
            return

        if existing_conn is not None:
            existing_conn.close()  # a read-write connection needs the file to itself

        serverless = is_serverless()
        if not serverless and self._can_write_destination():
            try:
                build_database(self.db_path, self.data_dir, self.csv_tables, force=self.rebuild)
                conn = duckdb.connect(str(self.db_path), read_only=True)
                self._serve(conn, "file")
                return
            except Exception as exc:  # noqa: BLE001 - fall back to a transient build
                logger.warning("In-place SQL build failed (%s); using transient database.", exc)
        else:
            logger.info(
                "Destination not usable for building (serverless=%s); using transient database.",
                serverless,
            )

        conn, storage = self._build_transient()
        transient_tables = _list_tables(conn)
        if len(existing_tables) > len(transient_tables):
            # The CSVs yield less than the DB we already have: prefer the existing one.
            conn.close()
            self._cleanup_transient()
            conn = duckdb.connect(str(self.db_path), read_only=True)
            storage = "file"
        self._serve(conn, storage)

    def _open_existing(self) -> tuple[duckdb.DuckDBPyConnection | None, set[str]]:
        if not self.db_path.exists():
            return None, set()
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not open existing SQL database read-only: %s", exc)
            return None, set()
        return conn, _list_tables(conn)

    def _can_write_destination(self) -> bool:
        directory = self.db_path.parent
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
        if not os.access(directory, os.W_OK | os.X_OK):
            return False
        if self.db_path.exists() and not os.access(self.db_path, os.W_OK):
            return False
        return True

    def _csv_bytes(self) -> int:
        total = 0
        for csv_file in self.csv_tables:
            try:
                total += (self.data_dir / csv_file).stat().st_size
            except OSError:
                continue
        return total

    def _build_transient(self) -> tuple[duckdb.DuckDBPyConnection, str]:
        if self._csv_bytes() > TRANSIENT_MEMORY_MAX_BYTES:
            try:
                self._transient_dir = Path(tempfile.mkdtemp(prefix="hybrid_chatbot_"))
                tmp_db = self._transient_dir / "hybrid_chatbot.duckdb"
                build_database(tmp_db, self.data_dir, self.csv_tables, force=True)
                if tmp_db.exists():
                    return duckdb.connect(str(tmp_db), read_only=True), "transient_file"
            except Exception as exc:  # noqa: BLE001
                logger.warning("Temp-file SQL build failed (%s); using in-memory.", exc)
            self._cleanup_transient()
        conn = duckdb.connect(":memory:")
        populate_connection(conn, self.data_dir, self.csv_tables, force=True)
        return conn, "transient_memory"

    def _cleanup_transient(self) -> None:
        if self._transient_dir is not None:
            shutil.rmtree(self._transient_dir, ignore_errors=True)
            self._transient_dir = None

    def _serve(self, conn: duckdb.DuckDBPyConnection, storage: str) -> None:
        tables = _list_tables(conn)
        available = [t for t in self.csv_tables.values() if t in tables]
        missing = [t for t in self.csv_tables.values() if t not in tables]
        if not available:
            conn.close()
            self._conn = None
            self._status = SQLStatus(
                state=STATE_UNAVAILABLE,
                available_tables=[],
                missing_tables=missing,
                error="No SQL tables could be built: no usable source CSV files were found.",
                storage="none",
            )
            return
        _lock_down(conn)
        self._conn = conn
        error = None
        if missing:
            missing_csv = [f for f, t in self.csv_tables.items() if t in missing]
            error = f"Missing tables (source CSV unavailable or unreadable): {', '.join(missing_csv)}"
        self._status = SQLStatus(
            state=STATE_DEGRADED if missing else STATE_READY,
            available_tables=available,
            missing_tables=missing,
            error=error,
            storage=storage,
        )

    # ── Queries ──────────────────────────────────────────────────────────────
    def missing_for(self, tables: list[str]) -> list[str]:
        """Tables from `tables` that the store cannot serve (all of them if unavailable)."""
        status = self.initialize()
        return [t for t in tables if t not in status.available_tables]

    def execute(self, sql: str, params: list | tuple | None = None) -> pd.DataFrame:
        """Run one read-only SELECT with bound parameters.

        This is the only place SQL text is executed for chatbot queries. It refuses
        anything that is not exactly one parsed SELECT statement over the store's own
        tables (no data-modifying CTEs, no file/URL table functions).
        """
        conn = self.connect()
        _assert_single_select(sql, conn, frozenset(self.csv_tables.values()))
        cursor = conn.cursor()  # per-call cursor: DuckDB connections are not thread-safe
        try:
            return cursor.execute(sql, list(params or [])).df()
        finally:
            cursor.close()

    def table_date_range(self, table: str, column: str) -> tuple[Optional[date], Optional[date]]:
        """(min, max) calendar date of one dated column of an available table."""
        if column not in DATE_COLUMNS.get(table, []):
            raise ValueError(f"{table}.{column} is not a known date column")
        if self.missing_for([table]):
            return (None, None)
        row = self.execute(
            f"SELECT MIN(CAST({_ident(column)} AS DATE)) AS lo, MAX(CAST({_ident(column)} AS DATE)) AS hi "
            f"FROM {_ident(table)}"
        ).iloc[0]
        if pd.isna(row["lo"]) or pd.isna(row["hi"]):
            return (None, None)
        return (_as_date(row["lo"]), _as_date(row["hi"]))

    def check_coverage(self, plan: SQLPlan) -> Coverage:
        """Decide whether the dataset covers the plan's date window and entities.

        Absence of data must never be reported as zero: a window outside the table's
        date range, or a subreddit/narrative that is not in the table, is `none`.
        """
        status = COVERAGE_NOT_APPLICABLE
        window: Optional[dict] = None
        table_range: Optional[dict] = None

        if plan.date_range and plan.date_source:
            table, column = plan.date_source
            window = {"start": plan.date_range[0], "end": plan.date_range[1]}
            try:
                start = date.fromisoformat(plan.date_range[0])
                end = date.fromisoformat(plan.date_range[1])
            except ValueError:
                return Coverage(
                    COVERAGE_NONE,
                    f"The requested window {plan.date_range[0]}..{plan.date_range[1]} contains invalid calendar dates.",
                    window,
                )
            if start > end:
                return Coverage(
                    COVERAGE_NONE,
                    f"The requested window {start.isoformat()}..{end.isoformat()} ends before it starts.",
                    window,
                )
            lo, hi = self.table_date_range(table, column)
            if lo is None or hi is None:
                return Coverage(COVERAGE_NONE, f"{table}.{column} has no dated rows.", window)
            table_range = {"table": table, "column": column, "start": lo.isoformat(), "end": hi.isoformat()}
            if end < lo or start > hi:
                return Coverage(
                    COVERAGE_NONE,
                    f"The requested window {start.isoformat()}..{end.isoformat()} falls entirely outside the "
                    f"dataset's coverage for {table} ({lo.isoformat()}..{hi.isoformat()}).",
                    window,
                    table_range,
                )
            if start < lo or end > hi:
                return Coverage(
                    COVERAGE_PARTIAL,
                    f"The requested window {start.isoformat()}..{end.isoformat()} extends beyond the dataset's "
                    f"coverage for {table} ({lo.isoformat()}..{hi.isoformat()}); the result reflects only the "
                    "covered part.",
                    window,
                    table_range,
                )
            status = COVERAGE_FULL

        for entity in plan.entities:
            if entity.match == "like":
                clause, value = f"{_ident(entity.column)} ILIKE ? ESCAPE '\\'", entity.value
            else:
                clause, value = f"lower({_ident(entity.column)}) = lower(?)", entity.value
            found = self.execute(f"SELECT 1 FROM {_ident(entity.table)} WHERE {clause} LIMIT 1", [value])
            if found.empty:
                shown = entity.display or (
                    entity.value.strip("%").replace("\\", "") if entity.match == "like" else entity.value
                )
                return Coverage(
                    COVERAGE_NONE,
                    f"The {entity.label} '{shown}' does not appear in {entity.table}.",
                    window,
                    table_range,
                )
            if status == COVERAGE_NOT_APPLICABLE:
                status = COVERAGE_FULL

        return Coverage(status, None, window, table_range)

    def valid_subreddits(self) -> set[str]:
        if self._valid_subreddits is not None:
            return self._valid_subreddits
        try:
            df = self.execute("SELECT DISTINCT subreddit FROM subreddit_domain_flow_v2")
            self._valid_subreddits = {str(s) for s in df["subreddit"].dropna().tolist()}
        except Exception:
            self._valid_subreddits = set()
        return self._valid_subreddits

    def dataset_date_range(self) -> tuple[Optional[date], Optional[date]]:
        """(min, max) calendar date across the dataset's dated tables, from the data."""
        if self._date_range is not None:
            return self._date_range
        status = self.initialize()
        lows: list[date] = []
        highs: list[date] = []
        for table, columns in DATE_COLUMNS.items():
            if table not in status.available_tables:
                continue
            for column in columns:
                try:
                    row = self.execute(
                        f"SELECT MIN(CAST({column} AS DATE)) AS lo, MAX(CAST({column} AS DATE)) AS hi "
                        f"FROM {table}"
                    ).iloc[0]
                except Exception:
                    continue
                if pd.notna(row["lo"]) and pd.notna(row["hi"]):
                    lows.append(_as_date(row["lo"]))
                    highs.append(_as_date(row["hi"]))
        if not lows:
            return (None, None)  # not cached: tables may become available after re-init
        self._date_range = (min(lows), max(highs))
        return self._date_range

    def dataset_max_date(self) -> Optional[date]:
        if self._max_date is None:
            self._max_date = self.dataset_date_range()[1]
        return self._max_date


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()


_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ident(name: str) -> str:
    """Validate an SQL identifier taken from the fixed templates / config (never user text)."""
    if not _IDENT_RE.match(name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return name


def _assert_single_select(
    sql: str,
    conn: duckdb.DuckDBPyConnection | None = None,
    allowed_tables: set[str] | frozenset[str] | None = None,
) -> None:
    """Refuse anything but exactly one plain SELECT, using DuckDB's own parser.

    * The text must parse to exactly one statement whose type is SELECT. This rejects
      data-modifying CTEs (`WITH x AS (...) DELETE ...`), INSERT/UPDATE/COPY/ATTACH/SET/
      PRAGMA-style statements and stacked statements, whatever comments or string
      literals they hide behind (a `;` inside a comment or literal is not a statement).
    * The parsed SELECT is then walked: table functions (read_csv*, read_text,
      read_parquet, glob, duckdb_*(), ...) are refused outright, and every table
      reference must be a bare identifier naming a CTE defined in the query or (when
      `allowed_tables` is given) one of the store's own tables. That also stops
      replacement scans such as `FROM '/etc/passwd.csv'` or a Python variable name.
    """
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("Only a single read-only SELECT statement may be executed.")
    own_conn = conn is None
    parse_conn = duckdb.connect(":memory:") if own_conn else conn
    try:
        try:
            statements = parse_conn.extract_statements(sql)
        except duckdb.Error as exc:
            raise ValueError(f"Only a single read-only SELECT statement may be executed: {exc}") from exc
        if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
            raise ValueError("Only a single read-only SELECT statement may be executed.")
        try:
            raw = parse_conn.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0]
            tree = json.loads(raw)
        except (duckdb.Error, ValueError, TypeError) as exc:
            raise ValueError(f"Only a single read-only SELECT statement may be executed: {exc}") from exc
    finally:
        if own_conn:
            parse_conn.close()
    if tree.get("error"):
        # PRAGMA / DESCRIBE / SHOW etc. parse as SELECT but are not plain queries.
        raise ValueError("Only a single read-only SELECT statement may be executed.")

    ctes: set[str] = set()
    tables: list[dict] = []
    functions: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            kind = node.get("type")
            if kind == "TABLE_FUNCTION":
                fn = node.get("function") or {}
                functions.append(str(fn.get("function_name") or "<table function>"))
            elif kind == "BASE_TABLE":
                tables.append(node)
            elif kind == "SHOW_REF":  # DESCRIBE / SHOW parse as a SELECT over a show node
                raise ValueError("Only a single read-only SELECT statement may be executed.")
            cte_map = node.get("cte_map")
            if isinstance(cte_map, dict):
                for entry in cte_map.get("map") or []:
                    if isinstance(entry, dict) and entry.get("key"):
                        ctes.add(str(entry["key"]).lower())
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(tree)
    if functions:
        raise ValueError(
            "Table functions (file/URL readers such as read_csv, read_text, glob) are not "
            f"allowed in chatbot queries: {', '.join(sorted(set(functions)))}"
        )
    allowed = {t.lower() for t in allowed_tables} if allowed_tables is not None else None
    for ref in tables:
        name = str(ref.get("table_name") or "")
        schema = str(ref.get("schema_name") or "")
        catalog = str(ref.get("catalog_name") or "")
        if catalog or schema.lower() not in ("", "main") or not _IDENT_RE.match(name):
            raise ValueError(f"Table reference {name!r} is not allowed in chatbot queries.")
        if name.lower() in ctes:
            continue
        if allowed is not None and name.lower() not in allowed:
            raise ValueError(f"Table {name!r} is not one of the chatbot's tables.")


class SQLTranslator:
    def __init__(self, valid_subreddits: set[str]):
        self.valid_subreddits = valid_subreddits

    def build_plan(self, query: str, reference_date: Optional[date] = None) -> Optional[SQLPlan]:
        """Keyword-template plan. Relative windows anchor to `reference_date`
        (the dataset's max date), not the wall clock."""
        plan = self._build_plan(query, reference_date)
        if plan is not None and not any(e.label == "narrative" for e in plan.entities):
            topic = _NARRATIVE_TOPIC.search(query)
            if topic:
                plan.notes.append(
                    f"No narrative filter was applied: '{topic.group(0).strip()}' is not a narrative "
                    "id, so this result is not limited to that narrative."
                )
        if plan is not None and _extract_date_range(query, reference_date) is None:
            phrase = _unparsed_time_phrase(query)
            if phrase:
                plan.notes.append(
                    f"No date filter was applied: the time reference '{phrase}' could not be "
                    "interpreted, so this result covers all available dates."
                )
        return plan

    def _build_plan(self, query: str, reference_date: Optional[date]) -> Optional[SQLPlan]:
        """Fixed keyword templates. User-derived values (subreddit, narrative, dates) are
        only ever bound as `?` parameters; the SQL text itself is constant."""
        q = query.lower().strip()
        narrative_token = _extract_narrative_token(query)
        subreddit = _extract_subreddit(query, self.valid_subreddits)
        date_range = _extract_date_range(query, reference_date)

        # Spike detection (for hybrid queries)
        if _has_any(q, ["spike", "spiked", "surge", "jump"]) and narrative_token:
            table = "graph_edge_intelligence_table"
            like = _narrative_like(narrative_token, table)
            date_sql, date_params = _date_filter("created_datetime", date_range)
            return SQLPlan(
                sql=(
                    "SELECT CAST(created_datetime AS DATE) AS date, COUNT(*) AS post_count "
                    f"FROM {table} "
                    f"WHERE narrative_id ILIKE ? ESCAPE '\\' {date_sql} "
                    "GROUP BY date "
                    "ORDER BY post_count DESC "
                    "LIMIT 1"
                ),
                description="Narrative spike date",
                tables=[table],
                params=[like, *date_params],
                kind="ranking",
                metrics=["date", "post_count"],
                date_range=date_range,
                date_source=(table, "created_datetime"),
                entities=[EntityFilter("narrative", table, "narrative_id", like, "like", narrative_token)],
            )
        if _has_any(q, ["spike", "spiked", "surge", "jump"]) and not narrative_token:
            table = "daily_volume_v2"
            date_sql, date_params = _date_filter("created_datetime", date_range)
            return SQLPlan(
                sql=(
                    "SELECT CAST(created_datetime AS DATE) AS date, post_count "
                    f"FROM {table} "
                    f"WHERE post_count IS NOT NULL {date_sql} "
                    "ORDER BY post_count DESC "
                    "LIMIT 1"
                ),
                description="Overall spike date",
                tables=[table],
                params=list(date_params),
                kind="ranking",
                metrics=["date", "post_count"],
                date_range=date_range,
                date_source=(table, "created_datetime"),
            )

        # Domain frequency
        if _has_any(q, ["domain", "domains"]) and _has_any(q, ["top", "most", "frequent", "frequently"]):
            table = "subreddit_domain_flow_v2"
            where, params, entities = "", [], []
            if subreddit:
                where = "WHERE lower(subreddit) = lower(?)"
                params.append(subreddit)
                entities.append(EntityFilter("subreddit", table, "subreddit", subreddit))
            return SQLPlan(
                sql=(
                    "SELECT domain, SUM(count) AS total_count "
                    f"FROM {table} "
                    f"{where} "
                    "GROUP BY domain "
                    "HAVING SUM(count) IS NOT NULL "
                    "ORDER BY total_count DESC "
                    "LIMIT 10"
                ),
                description="Top domains by frequency",
                tables=[table],
                params=params,
                kind="ranking",
                metrics=["total_count"],
                entities=entities,
            )

        # Echo chamber score
        if _has_any(q, ["echo chamber", "echo-chamber", "echo"]):
            top_only = _has_any(q, ["highest", "top", "most"])
            return SQLPlan(
                sql=(
                    "SELECT subreddit, TRY_CAST(lift AS DOUBLE) AS lift "
                    "FROM echo_chamber_scores "
                    "WHERE isfinite(TRY_CAST(lift AS DOUBLE)) "
                    "ORDER BY lift DESC "
                    f"LIMIT {1 if top_only else 10}"
                ),
                description="Highest echo chamber score" if top_only else "Echo chamber scores",
                tables=["echo_chamber_scores"],
                kind="ranking",
                metrics=["subreddit", "lift"],
            )

        # Dominant narratives in a subreddit
        if _has_any(q, ["narrative", "narratives"]) and subreddit and _has_any(q, ["dominant", "main", "top", "most"]):
            return SQLPlan(
                sql=(
                    "SELECT nr.representative_title, nr.primary_domain, COUNT(*) AS post_count "
                    "FROM narrative_diffusion_table nd "
                    "JOIN narrative_registry nr ON nd.narrative_id = nr.narrative_id "
                    "WHERE lower(nd.subreddit) = lower(?) "
                    "GROUP BY nr.representative_title, nr.primary_domain "
                    "ORDER BY post_count DESC "
                    "LIMIT 10"
                ),
                description="Dominant narratives by subreddit",
                tables=["narrative_diffusion_table", "narrative_registry"],
                params=[subreddit],
                kind="ranking",
                metrics=["post_count"],
                entities=[EntityFilter("subreddit", "narrative_diffusion_table", "subreddit", subreddit)],
            )

        # Subreddit amplification for a narrative
        if _has_any(q, ["subreddit", "subreddits"]) and narrative_token and _has_any(q, ["most", "top", "amplified", "amplify"]):
            table = "narrative_diffusion_table"
            like = _narrative_like(narrative_token, table)
            return SQLPlan(
                sql=(
                    "SELECT subreddit, COUNT(*) AS post_count "
                    f"FROM {table} "
                    "WHERE narrative_id ILIKE ? ESCAPE '\\' "
                    "GROUP BY subreddit "
                    "ORDER BY post_count DESC "
                    "LIMIT 10"
                ),
                description="Subreddit amplification for narrative",
                tables=[table],
                params=[like],
                kind="ranking",
                metrics=["subreddit", "post_count"],
                entities=[EntityFilter("narrative", table, "narrative_id", like, "like", narrative_token)],
            )

        # Narrative volume (highest)
        if _has_any(q, ["highest", "most", "top"]) and _has_any(q, ["narrative", "volume"]):
            table = "graph_edge_intelligence_table"
            date_sql, date_params = _date_filter("created_datetime", date_range)
            return SQLPlan(
                sql=(
                    "SELECT narrative_id, COUNT(*) AS post_count "
                    f"FROM {table} "
                    f"WHERE narrative_id IS NOT NULL {date_sql} "
                    "GROUP BY narrative_id "
                    "ORDER BY post_count DESC "
                    "LIMIT 1"
                ),
                description="Highest narrative volume",
                tables=[table],
                params=list(date_params),
                kind="ranking",
                metrics=["narrative_id", "post_count"],
                date_range=date_range,
                date_source=(table, "created_datetime"),
            )

        # Trend over time
        if _has_any(q, ["trend", "over time", "time series"]):
            if narrative_token:
                table = "graph_edge_intelligence_table"
                like = _narrative_like(narrative_token, table)
                date_sql, date_params = _date_filter("created_datetime", date_range)
                return SQLPlan(
                    sql=(
                        "SELECT CAST(created_datetime AS DATE) AS date, COUNT(*) AS post_count "
                        f"FROM {table} "
                        f"WHERE narrative_id ILIKE ? ESCAPE '\\' {date_sql} "
                        "GROUP BY date "
                        "ORDER BY date"
                    ),
                    description="Narrative trend over time",
                    tables=[table],
                    params=[like, *date_params],
                    kind="series",
                    metrics=["date", "post_count"],
                    date_range=date_range,
                    date_source=(table, "created_datetime"),
                    entities=[EntityFilter("narrative", table, "narrative_id", like, "like", narrative_token)],
                )

            table = "daily_volume_v2"
            date_sql, date_params = _date_filter("created_datetime", date_range)
            return SQLPlan(
                sql=(
                    "SELECT CAST(created_datetime AS DATE) AS date, post_count "
                    f"FROM {table} "
                    f"WHERE post_count IS NOT NULL {date_sql} "
                    "ORDER BY date"
                ),
                description="Overall volume trend",
                tables=[table],
                params=list(date_params),
                kind="series",
                metrics=["date", "post_count"],
                date_range=date_range,
                date_source=(table, "created_datetime"),
            )

        # Generic post counts
        if _has_any(q, ["how many", "count", "number of"]) and _has_any(q, ["post", "posts"]):
            table = "clean_posts"
            where_parts: list[str] = []
            params: list = []
            entities = []
            if subreddit:
                where_parts.append("lower(subreddit) = lower(?)")
                params.append(subreddit)
                entities.append(EntityFilter("subreddit", table, "subreddit", subreddit))
            if date_range:
                date_sql, date_params = _date_filter("created_datetime", date_range)
                where_parts.append(date_sql[len("AND "):])
                params.extend(date_params)
            where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""
            return SQLPlan(
                sql=f"SELECT COUNT(*) AS post_count FROM {table} {where_clause}",
                description="Post count",
                tables=[table],
                params=params,
                kind="count",
                metrics=["post_count"],
                date_range=date_range,
                date_source=(table, "created_datetime") if date_range else None,
                entities=entities,
            )

        # Avg score by subreddit
        if _has_any(q, ["average score", "avg score", "average"]):
            table = "subreddit_intelligence_summary"
            if subreddit:
                return SQLPlan(
                    sql=(
                        "SELECT subreddit, TRY_CAST(avg_score AS DOUBLE) AS avg_score "
                        f"FROM {table} "
                        "WHERE lower(subreddit) = lower(?)"
                    ),
                    description="Average score",
                    tables=[table],
                    params=[subreddit],
                    kind="aggregate",
                    metrics=["avg_score"],
                    entities=[EntityFilter("subreddit", table, "subreddit", subreddit)],
                )
            return SQLPlan(
                sql=(
                    "SELECT AVG(TRY_CAST(avg_score AS DOUBLE)) "
                    "FILTER (WHERE isfinite(TRY_CAST(avg_score AS DOUBLE))) AS avg_score "
                    f"FROM {table}"
                ),
                description="Average score",
                tables=[table],
                kind="aggregate",
                metrics=["avg_score"],
            )

        return None


def parse_date_range(query: str, reference_date: Optional[date] = None) -> Optional[Tuple[str, str]]:
    """Public helper for extracting date ranges from user queries."""
    return _extract_date_range(query, reference_date)


# ── Helpers ─────────────────────────────────────────────────────────────────-

def _has_any(text: str, needles: list[str]) -> bool:
    return any(n in text for n in needles)


# Narrative ids as they appear in the data:
#   narrative_registry / narrative_diffusion_table : "0.0_salon.com", "128.0_blackrosefed.org"
#                                                    or "<domain>_<domain>" (no cluster number)
#   graph_edge_intelligence_table                  : "128_blackrosefed.org", "67_youtu.be"
# Only tokens shaped like one of those (or explicitly quoted / "id"-prefixed) count as
# a narrative entity; an ordinary word after "narrative" ("spiked", "over", "about")
# does not.
_NARRATIVE_FULL_ID = re.compile(
    r"(?<![A-Za-z0-9_.\-])(\d+(?:\.\d+)?_[A-Za-z0-9][A-Za-z0-9\-]*(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,})(?![A-Za-z0-9_\-])"
)
_NARRATIVE_DOMAIN_ID = re.compile(
    r"(?<![A-Za-z0-9_.\-])([A-Za-z0-9][A-Za-z0-9\-]*(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}_"
    r"[A-Za-z0-9][A-Za-z0-9\-]*(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,})(?![A-Za-z0-9_\-])"
)
_NARRATIVE_QUOTED = re.compile(
    r"\bnarrative(?:\s+id)?\s*[:=]?\s*[\"'\u201c\u2018`]([^\"'\u201d\u2019`]{1,80})[\"'\u201d\u2019`]",
    re.IGNORECASE,
)
_NARRATIVE_NUMBER = re.compile(
    r"\bnarrative\s+(?:(?:id|no\.?|number|num)\s*)?[:#=]?\s*(\d{1,4})\b(?![.,]?\d)", re.IGNORECASE
)
_NARRATIVE_DOMAIN = re.compile(
    r"\bnarrative\s+(?:id\s*)?[:=]?\s*([A-Za-z0-9][A-Za-z0-9\-]*(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,})(?![A-Za-z0-9_\-])",
    re.IGNORECASE,
)
_NARRATIVE_EXPLICIT_ID = re.compile(r"\bnarrative\s+id\s*[:=#]?\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)", re.IGNORECASE)
_NARRATIVE_N_PREFIX = re.compile(r"\bN(\d+)\b", re.IGNORECASE)
_NARRATIVE_TOPIC = re.compile(
    r"\bnarratives?\s+(?:about|regarding|concerning|related to|on|around|called|named|titled)\s+[^?.!,;]{1,40}",
    re.IGNORECASE,
)
_NARRATIVE_STOPWORDS = frozenset(
    "a an the this that these those it its is are was were be been being of on in at to for from by with "
    "about regarding around over under into onto across during after before since until between among "
    "and or but not no any all each every some which what who whom whose when where why how "
    "spiked spike spikes surged surge jumped jump trend trending trends volume volumes top most highest "
    "dominant main biggest largest amplified amplify amplifies spread spreading posts post count "
    "id ids number name named called titled one two".split()
)


def _extract_narrative_token(query: str) -> Optional[str]:
    """The narrative id/name the question refers to, or None.

    Only an id-shaped token (see formats above), a bare cluster number ("narrative 128",
    "N128"), a domain ("narrative salon.com"), a quoted name, or an explicit
    "narrative id <x>" counts. Anything else leaves the question un-scoped.
    """
    m = _NARRATIVE_QUOTED.search(query)
    if m and m.group(1).strip():
        return m.group(1).strip()
    for pattern in (_NARRATIVE_FULL_ID, _NARRATIVE_DOMAIN_ID):
        m = pattern.search(query)
        if m:
            return m.group(1)
    m = _NARRATIVE_NUMBER.search(query)
    if m and not re.fullmatch(r"(?:19|20)\d{2}", m.group(1)):
        return f"N{int(m.group(1))}"
    m = _NARRATIVE_DOMAIN.search(query)
    if m:
        return m.group(1)
    m = _NARRATIVE_EXPLICIT_ID.search(query)
    if m:
        token = m.group(1).rstrip(".-_")
        if token and token.lower() not in _NARRATIVE_STOPWORDS:
            return token
    m = _NARRATIVE_N_PREFIX.search(query)
    if m:
        return f"N{int(m.group(1))}"
    return None


def _narrative_like(token: str, table: str = "narrative_diffusion_table") -> str:
    """ILIKE pattern (bound as a parameter, used with ESCAPE '\\') for a narrative token,
    shaped for the id format `table` actually uses (see formats above)."""
    token = token.strip()
    graph_style = table == "graph_edge_intelligence_table"

    def esc(text: str) -> str:
        return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    m = re.fullmatch(r"(\d+)(?:\.\d+)?_(.+)", token)
    if m:
        cluster, rest = int(m.group(1)), esc(m.group(2))
        return f"{cluster}\\_{rest}" if graph_style else f"{cluster}.%\\_{rest}"
    m = re.fullmatch(r"N?(\d+)", token, re.IGNORECASE)
    if m:
        cluster = int(m.group(1))
        return f"{cluster}\\_%" if graph_style else f"{cluster}.%"
    return f"%{esc(token)}%"


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
    # Relative phrases are anchored to the dataset's max date (reference_date); the
    # wall clock is only a last resort for callers that have no dataset.
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


_MONTHS = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
    r"sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
_TIME_CUE = re.compile(
    r"\b(?:"
    rf"(?:(?:early|mid|late)[\s-]+)?(?:{_MONTHS})"  # a month name
    r"|(?:(?:early|mid|late)[\s-]+|(?:in|during|of|since|from|until|by|before|after)\s+)may"
    r"|may\s+(?:19|20)\d{2}"
    r"|(?:19|20)\d{2}-\d{2}-\d{2}|(?:19|20)\d{2}"  # a single ISO date / a year
    r"|q[1-4]"
    r"|(?:last|this|next|previous|past|prior|current)\s+(?:\w+\s+)?(?:day|week|month|quarter|year|weekend)s?"
    r"|\d+\s+(?:day|week|month|year)s?\s+ago"
    r"|yesterday|today|tonight|recently|lately"
    r")\b",
    re.IGNORECASE,
)


def _unparsed_time_phrase(query: str) -> Optional[str]:
    """The time-like phrase in `query`, for a question whose date window could not be parsed."""
    m = _TIME_CUE.search(query)
    return m.group(0).strip() if m else None


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
        month = month_map[month_token[:3]]
        if month_token == "may" and not re.search(
            r"\b(?:in|during|of|since|from|until|early|mid|late)\s+may\b", query
        ):
            return None  # the modal verb ("which narratives may have spiked"), not the month
        # A bare month means its most recent occurrence on or before the anchor date.
        anchor = reference_date or date.today()
        year = anchor.year if month <= anchor.month else anchor.year - 1
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


def _date_filter(column: str, date_range: Optional[Tuple[str, str]]) -> tuple[str, list[str]]:
    """('AND CAST(col AS DATE) BETWEEN ? AND ?', [start, end]); both bound as parameters."""
    if not date_range:
        return "", []
    return f"AND CAST({_ident(column)} AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)", [date_range[0], date_range[1]]
