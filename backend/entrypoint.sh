#!/bin/sh
set -e

# Environment:
#   DATA_PATH   runtime data directory (default /app/data, the persistent disk).
#   SEED_PATH   image copy of the data files (default /app/seed_data).
#   SEED_FORCE  set to 1 to overwrite existing files on DATA_PATH with the seed
#               copy. Unset (default) only copies seed files that are missing.
#   PORT        uvicorn port (default 8000).
#   STREAMGRAPH2_DUCKDB_PATH defaults to the persistent data directory.

DATA_PATH="${DATA_PATH:-/app/data}"
SEED_PATH="${SEED_PATH:-/app/seed_data}"
STREAMGRAPH2_DUCKDB_PATH="${STREAMGRAPH2_DUCKDB_PATH:-$DATA_PATH/streamgraph2.duckdb}"
export DATA_PATH STREAMGRAPH2_DUCKDB_PATH

mkdir -p "$DATA_PATH"

# Seed the data directory from the image. Files already present on the disk are
# kept unless SEED_FORCE=1, so newly added CSVs reach an existing disk without
# replacing data that may have been rebuilt or edited there.
if [ -d "$SEED_PATH" ]; then
  if [ ! -f "$DATA_PATH/analysis_v2.db" ]; then
    echo "[entrypoint] Database missing in $DATA_PATH. Initializing from seed data..."
  fi
  seeded=0
  skipped=0
  while IFS= read -r rel; do
    src="$SEED_PATH/$rel"
    dest="$DATA_PATH/$rel"
    if [ "${SEED_FORCE:-0}" = "1" ] || [ ! -e "$dest" ]; then
      mkdir -p "$(dirname "$dest")"
      cp -p "$src" "$dest" || { echo "[entrypoint] Failed to seed $rel" >&2; exit 1; }
      seeded=$((seeded + 1))
      echo "[entrypoint] Seeded $rel"
    else
      skipped=$((skipped + 1))
    fi
  done <<SEEDLIST
$(cd "$SEED_PATH" && find . -type f | sed 's#^\./##')
SEEDLIST
  echo "[entrypoint] Seed complete: $seeded copied, $skipped already present (SEED_FORCE=${SEED_FORCE:-0})."
fi

# Patch DuckDB views to fix hardcoded local paths
echo "[entrypoint] Patching DuckDB intelligence views..."
python patch_db.py

# Keep admission quotas, background-job slots, and database connections in one
# process even when the platform supplies a larger WEB_CONCURRENCY value.
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
