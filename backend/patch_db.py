import duckdb
import os
from pathlib import Path

# Path configuration must match intelligence.py logic
_RENDER_PERSISTENT = Path("/app/data")
_RENDER_SEED = Path("/app/seed_data")
# For local fallback
_REL_DATA = Path(__file__).resolve().parents[1] / "data"

if _RENDER_PERSISTENT.exists():
    DEFAULT_DATA_PATH = _RENDER_PERSISTENT
elif _RENDER_SEED.exists():
    DEFAULT_DATA_PATH = _RENDER_SEED
else:
    DEFAULT_DATA_PATH = _REL_DATA

DB_PATH = Path(os.getenv("DATA_PATH", str(DEFAULT_DATA_PATH))) / "analysis_v2.db"

def patch_db():
    if not DB_PATH.exists():
        print(f"[patch] Database not found at {DB_PATH}")
        return

    print(f"[patch] Patching DuckDB views in {DB_PATH} using data from {DEFAULT_DATA_PATH}")
    try:
        con = duckdb.connect(str(DB_PATH), read_only=False)
        csvs = {
            "narratives": "narrative_intelligence_summary.csv",
            "topics": "narrative_topic_mapping.csv",
            "chains": "narrative_spread_chain_table.csv",
            "amplification": "author_amplification_summary.csv",
            "daily_volume": "daily_volume_v2.csv",
            "echo_chambers": "echo_chamber_scores.csv",
            "ideological_matrix": "ideological_distance_matrix.csv"
        }
        for view_name, fname in csvs.items():
            fpath = DEFAULT_DATA_PATH / fname
            if fpath.exists():
                print(f"[patch] Updating view {view_name} -> {fname}")
                con.execute(f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_csv_auto('{fpath.resolve().as_posix()}')")
        con.close()
        print("[patch] Patching complete.")
    except Exception as e:
        print(f"[patch] Error during patching: {e}")

if __name__ == "__main__":
    patch_db()
