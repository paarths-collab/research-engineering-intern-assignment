"""
patch_db.py — Startup script to import CSV data as PERSISTENT TABLES in DuckDB.

This must run BEFORE the FastAPI server starts.

IMPORTANT: DuckDB views are connection-scoped (session-only) and do NOT survive
across separate connections. We must use CREATE OR REPLACE TABLE (not VIEW) so
the data is fully persisted inside analysis_v2.db and accessible to read-only
connections opened by intelligence.py.
"""
import duckdb
import os
from pathlib import Path

# Path configuration — must match intelligence.py logic
_RENDER_PERSISTENT = Path("/app/data")
_RENDER_SEED = Path("/app/seed_data")
_REL_DATA = Path(__file__).resolve().parents[1] / "data"

if _RENDER_PERSISTENT.exists():
    DEFAULT_DATA_PATH = _RENDER_PERSISTENT
elif _RENDER_SEED.exists():
    DEFAULT_DATA_PATH = _RENDER_SEED
else:
    DEFAULT_DATA_PATH = _REL_DATA

DB_PATH = Path(os.getenv("DATA_PATH", str(DEFAULT_DATA_PATH))) / "analysis_v2.db"

# Map of table name → CSV filename
TABLES = {
    "narratives": "narrative_intelligence_summary.csv",
    "topics": "narrative_topic_mapping.csv",
    "chains": "narrative_spread_chain_table.csv",
    "amplification": "author_amplification_summary.csv",
    "daily_volume": "daily_volume_v2.csv",
    "echo_chambers": "echo_chamber_scores.csv",
    "ideological_matrix": "ideological_distance_matrix.csv",
    "posts": "clean_posts.csv",
    "subreddit_edges": "graph_edge_intelligence_table.csv",
}


def patch_db():
    if not DB_PATH.exists():
        print(f"[patch] Database not found at {DB_PATH}. Trying to create it.")
    
    data_path_override = os.getenv("DATA_PATH")
    data_path = Path(data_path_override) if data_path_override else DEFAULT_DATA_PATH
    
    print(f"[patch] Importing CSV data as tables into {DB_PATH}")
    print(f"[patch] Reading CSVs from {data_path}")
    
    try:
        # Open DB in read-write mode to create/replace tables
        con = duckdb.connect(str(DB_PATH), read_only=False)
        
        imported = []
        skipped = []
        for table_name, fname in TABLES.items():
            fpath = data_path / fname
            if fpath.exists():
                print(f"[patch] Importing {fname} -> table '{table_name}'")
                # DuckDB won't replace a VIEW with a TABLE — drop first
                try:
                    con.execute(f"DROP VIEW IF EXISTS {table_name}")
                except Exception:
                    pass
                con.execute(f"""
                    CREATE OR REPLACE TABLE {table_name} AS
                    SELECT * FROM read_csv_auto('{fpath.resolve().as_posix()}')
                """)
                count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                print(f"[patch]   -> {count} rows imported")
                imported.append(table_name)
            else:
                print(f"[patch] WARNING: CSV not found at {fpath}, skipping '{table_name}'")
                skipped.append(table_name)
        
        con.close()
        print(f"[patch] Done. Imported: {imported}, Skipped: {skipped}")
        
    except Exception as e:
        print(f"[patch] ERROR during patching: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    patch_db()
