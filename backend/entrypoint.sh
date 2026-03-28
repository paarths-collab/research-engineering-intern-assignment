#!/bin/sh
set -e

DATA_PATH="${DATA_PATH:-/app/data}"
SEED_PATH="/app/seed_data"

mkdir -p "$DATA_PATH"

# Seed persistent data disk if database is missing.
if [ -d "$SEED_PATH" ] && [ ! -f "$DATA_PATH/analysis_v2.db" ]; then
  echo "[entrypoint] Database missing in $DATA_PATH. Initializing from seed data..."
  cp -a "$SEED_PATH/." "$DATA_PATH/"
fi

# Patch DuckDB views to fix hardcoded local paths
echo "[entrypoint] Patching DuckDB intelligence views..."
python patch_db.py

exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
