import sys
import argparse
import re
import duckdb

# ── CLI ────────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--db",     default="data/analysis_v2.db", help="Path to DuckDB file")
parser.add_argument("--domain", default="breitbart.com",  help="Domain to filter on")
parser.add_argument("--start",  default="2025-02-14",     help="Start date (inclusive) YYYY-MM-DD")
parser.add_argument("--end",    default="2025-02-18",     help="End date   (inclusive) YYYY-MM-DD")
parser.add_argument("--limit",  default=50, type=int,     help="Max rows to return")
args = parser.parse_args()

DOMAIN = args.domain
START  = args.start
END    = args.end

# ── Connect ────────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  DB      : {args.db}")
print(f"  Domain  : {DOMAIN}")
print(f"  Window  : {START}  →  {END}")
print(f"{'='*60}\n")

con = duckdb.connect(args.db, read_only=True)

# ── Step 1 · Discover schema ───────────────────────────────────────────────────
print("── Schema Discovery ──────────────────────────────────────────")
tables = con.execute("SHOW TABLES").fetchdf()
print(tables.to_string(index=False), "\n")

for tbl in tables["name"]:
    cols = con.execute(f"DESCRIBE {tbl}").fetchdf()
    print(f"  [{tbl}]")
    print(cols[["column_name", "column_type"]].to_string(index=False))
    print()

# ── Step 2 · Find the right table + columns ───────────────────────────────────
URL_COLS  = ["url", "link", "href", "external_url", "outbound_url", "shared_url"]
DATE_COLS = ["created_utc", "timestamp", "date", "posted_at", "created_at", "created", "created_datetime"]

def find_column(col_list, candidates):
    """Return first candidate that exists in col_list (case-insensitive)."""
    lower = [c.lower() for c in col_list]
    for candidate in candidates:
        if candidate.lower() in lower:
            return col_list[lower.index(candidate.lower())]
    return None

target_table = None
url_col      = None
date_col     = None

for tbl in tables["name"]:
    cols     = con.execute(f"DESCRIBE {tbl}").fetchdf()
    col_names = list(cols["column_name"])
    u = find_column(col_names, URL_COLS)
    d = find_column(col_names, DATE_COLS)
    if u and d:
        target_table = tbl
        url_col      = u
        date_col     = d
        break

if not target_table:
    print("❌  Could not auto-detect a table with both a URL column and a date column.")
    print("    Tables available:", list(tables["name"]))
    print("    Edit URL_COLS / DATE_COLS at the top of this script to match your schema.")
    sys.exit(1)

print(f"✅  Using table  : {target_table}")
print(f"    URL column   : {url_col}")
print(f"    Date column  : {date_col}\n")

# ── Step 3 · Build & run the query ────────────────────────────────────────────
col_type = con.execute(
    f"SELECT column_type FROM (DESCRIBE {target_table}) WHERE column_name = '{date_col}'"
).fetchone()[0].upper()

IS_EPOCH = any(t in col_type for t in ("INT", "BIGINT", "DOUBLE", "FLOAT", "HUGEINT"))

if IS_EPOCH:
    date_filter = f"""
        epoch_ms(CAST({date_col} AS BIGINT) * 1000) >= TIMESTAMP '{START} 00:00:00'
    AND epoch_ms(CAST({date_col} AS BIGINT) * 1000) <= TIMESTAMP '{END} 23:59:59'
    """
else:
    date_filter = f"""
        CAST({date_col} AS DATE) BETWEEN DATE '{START}' AND DATE '{END}'
    """

query = f"""
SELECT
    {url_col}                               AS url,
    {"epoch_ms(CAST(" + date_col + " AS BIGINT)*1000)" if IS_EPOCH else date_col}
                                            AS posted_at
FROM  {target_table}
WHERE {url_col} LIKE '%{DOMAIN}%'
  AND {date_filter.strip()}
ORDER BY posted_at DESC
LIMIT {args.limit};
"""

print("── SQL ───────────────────────────────────────────────────────")
print(query)
print("── Results ───────────────────────────────────────────────────")

try:
    df = con.execute(query).fetchdf()
except Exception as e:
    print(f"❌  Query failed: {e}")
    print("\nTry running the schema discovery output above and adjust the script.")
    sys.exit(1)

if df.empty:
    print(f"⚠️   No rows found for domain='{DOMAIN}' in window {START} → {END}.")
    print("    Possible causes:")
    print("    • Domain name mismatch (try 'breitbart' without '.com')")
    print("    • Date window out of range — run a broader test:")
    sample = con.execute(
        f"SELECT MIN({date_col}), MAX({date_col}) FROM {target_table} LIMIT 1"
    ).fetchone()
    print(f"      date range in DB: {sample[0]}  →  {sample[1]}")
    sys.exit(1)

# ── Step 4 · Validate & print ─────────────────────────────────────────────────
URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)

valid_urls = []
for _, row in df.iterrows():
    raw = str(row["url"]).strip()
    if URL_RE.match(raw):
        valid_urls.append((raw, row["posted_at"]))

print(f"\n  Found {len(df)} rows · {len(valid_urls)} valid-format URLs\n")

for i, (url, ts) in enumerate(valid_urls, 1):
    print(f"  [{i:>3}]  {ts}   {url}")

print()

# ── Step 5 · Pass / Fail verdict ──────────────────────────────────────────────
MIN_VALID = 5
if len(valid_urls) >= MIN_VALID:
    print(f"✅  SUBTASK 1 PASSED — {len(valid_urls)} valid Breitbart URLs extracted.")
else:
    print(f"❌  SUBTASK 1 FAILED — only {len(valid_urls)} valid URLs found (need {MIN_VALID}).")
    print("    Check domain spelling, date range, or URL column values.")

con.close()
