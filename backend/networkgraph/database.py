import os
import duckdb
import logging
from pathlib import Path
from fastapi import HTTPException
from contextlib import contextmanager

log = logging.getLogger("sntis.database")

_RENDER_PERSISTENT = Path("/app/data")
_RENDER_SEED = Path("/app/seed_data")
_REL_DATA = Path(__file__).resolve().parents[2] / "data" 

if _RENDER_PERSISTENT.exists():
    DEFAULT_DATA_PATH = _RENDER_PERSISTENT
elif _RENDER_SEED.exists():
    DEFAULT_DATA_PATH = _RENDER_SEED
else:
    DEFAULT_DATA_PATH = _REL_DATA

DB_PATH = Path(os.getenv("DATA_PATH", str(DEFAULT_DATA_PATH))) / "analysis_v2.db"
DB_PATH = DB_PATH.resolve()

@contextmanager
def get_db():
    if not DB_PATH.exists():
        log.error(f"Database not found at {DB_PATH}")
        raise HTTPException(
            status_code=500,
            detail=f"Database not found at {DB_PATH.absolute()}"
        )

    log.debug(f"Opening DuckDB: {DB_PATH}")
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        yield con
    finally:
        con.close()
