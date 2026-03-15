#!/bin/sh
set -e

DATA_PATH="${DATA_PATH:-/app/data}"
SEED_PATH="/app/seed_data"

mkdir -p "$DATA_PATH"

# Seed persistent data disk only on first boot (or if empty).
if [ -d "$SEED_PATH" ] && [ -z "$(ls -A "$DATA_PATH" 2>/dev/null)" ]; then
  echo "[entrypoint] Initializing DATA_PATH from seed data..."
  cp -a "$SEED_PATH/." "$DATA_PATH/"
fi

exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
