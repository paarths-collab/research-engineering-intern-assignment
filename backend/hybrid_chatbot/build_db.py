"""
hybrid_chatbot/build_db.py
--------------------------
Build the chatbot's DuckDB file from the source CSVs.

    cd backend && python -m hybrid_chatbot.build_db [--db PATH] [--force] [--data-dir DIR]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import CSV_TABLES, resolve_data_dir, resolve_db_path
from .sql_engine import build_database


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the hybrid chatbot DuckDB from CSVs.")
    parser.add_argument("--db", type=Path, default=None, help="Output DuckDB path (default: configured path).")
    parser.add_argument("--data-dir", type=Path, default=None, help="Directory holding the source CSVs.")
    parser.add_argument("--force", action="store_true", help="Rebuild every table even if it already exists.")
    args = parser.parse_args(argv)

    db_path = args.db or resolve_db_path()
    data_dir = args.data_dir or resolve_data_dir()
    counts = build_database(db_path, data_dir, CSV_TABLES, force=args.force)

    print(f"Database: {db_path}")
    for table in CSV_TABLES.values():
        if table in counts:
            print(f"  {table}: {counts[table]} rows")
        else:
            print(f"  {table}: MISSING (source CSV not found or unreadable)")
    missing = [t for t in CSV_TABLES.values() if t not in counts]
    if missing:
        print(f"{len(missing)} table(s) missing.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
