import duckdb
from pathlib import Path
from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

_conn: duckdb.DuckDBPyConnection | None = None


def get_connection() -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is None:
        Path(settings.DATA_DIR).mkdir(exist_ok=True)
        _conn = duckdb.connect(settings.DUCKDB_PATH)
        logger.info(f"DuckDB connected: {settings.DUCKDB_PATH}")
    return _conn


def init_db() -> None:
    """Create all tables if they don't exist."""
    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS raw_posts (
            id              VARCHAR PRIMARY KEY,
            title           VARCHAR NOT NULL,
            subreddit       VARCHAR,
            score           INTEGER DEFAULT 0,
            num_comments    INTEGER DEFAULT 0,
            created_utc     DOUBLE,
            author          VARCHAR,
            url             VARCHAR,
            engagement_score DOUBLE DEFAULT 0,
            velocity_score  DOUBLE DEFAULT 0,
            run_date        DATE DEFAULT CURRENT_DATE,
            processed       BOOLEAN DEFAULT FALSE,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS geo_resolutions (
            id          VARCHAR PRIMARY KEY,
            post_id     VARCHAR,
            raw_term    VARCHAR,
            resolved    VARCHAR,
            lat         DOUBLE,
            lon         DOUBLE,
            geo_type    VARCHAR,
            is_valid    BOOLEAN DEFAULT TRUE,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS structured_events (
            id                  VARCHAR PRIMARY KEY,
            post_id             VARCHAR,
            event_type          VARCHAR,
            primary_location    VARCHAR,
            secondary_locations VARCHAR,
            key_entities        VARCHAR,
            search_queries      VARCHAR,
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS news_articles (
            id              VARCHAR PRIMARY KEY,
            event_id        VARCHAR,
            title           VARCHAR,
            snippet         VARCHAR,
            url             VARCHAR,
            source          VARCHAR,
            published_at    VARCHAR,
            is_trusted      BOOLEAN DEFAULT FALSE,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS event_clusters (
            cluster_id          VARCHAR PRIMARY KEY,
            post_ids            VARCHAR,
            primary_location    VARCHAR,
            lat                 DOUBLE,
            lon                 DOUBLE,
            average_impact      DOUBLE,
            dominant_sentiment  VARCHAR,
            risk_level          VARCHAR,
            escalation_level    VARCHAR,
            summary             VARCHAR,
            strategic_implications VARCHAR,
            news_count          INTEGER DEFAULT 0,
            confidence          VARCHAR,
            run_date            DATE DEFAULT CURRENT_DATE,
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    logger.info("Database schema initialised")


def close_db() -> None:
    global _conn
    if _conn:
        _conn.close()
        _conn = None
