"""
ingest.py — One-time baseline data loader.

Run once to populate Neon from CSV files.

Usage:
    python ingest.py --posts data/clean_posts.csv
                     --embeddings data/title_embeddings_v2.npy
                     --volume data/daily_volume_v2.csv
                     --domains data/clean_top_distinctive_domains.csv
                     --flow data/subreddit_domain_flow_v2.csv
                     --echo data/echo_chamber_scores.csv
"""

import asyncio
import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

from streamgraph2.logic import db
from streamgraph2.data.config import DATABASE_URL


# ── Helpers ───────────────────────────────────────────────────

def parse_ts(val: str) -> datetime:
    """Best-effort timestamp parse for reddit UTC columns."""
    for fmt in ("%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse timestamp: {val!r}")


# ── Ingestors ─────────────────────────────────────────────────

async def ingest_posts(posts_path: str, emb_path: str):
    print(f"→ Loading posts from {posts_path}")
    embeddings = None
    if emb_path and Path(emb_path).exists():
        embeddings = np.load(emb_path)
        print(f"  Embeddings shape: {embeddings.shape}")

    rows = []
    with open(posts_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if embeddings is not None and len(embeddings) != len(rows):
        print(f"  ⚠ Row count mismatch: {len(rows)} posts vs {len(embeddings)} embeddings. Using available embeddings.")

    inserted = skipped = 0
    batch = []
    for i, row in enumerate(rows):
        emb = embeddings[i].tolist() if embeddings is not None and i < len(embeddings) else None
        try:
            batch.append((
                row.get("id") or row.get("post_id") or f"hist_{i}",
                row.get("subreddit", "unknown"),
                row.get("title", ""),
                row.get("author", ""),
                int(row.get("score", 0) or 0),
                int(row.get("num_comments", 0) or 0),
               parse_ts(row["created_datetime"]),
                "historical",
                None,  # url
                db.vec_to_pg(emb) if emb else None
            ))
            
            if len(batch) >= 500:
                await db.upsert_posts_bulk(batch)
                inserted += len(batch)
                batch = []
                print(f"  {i+1}/{len(rows)} processed…")
        except Exception as e:
            skipped += 1
            if skipped <= 5:
                print(f"  ✗ Row {i}: {e}")

    if batch:
        try:
            await db.upsert_posts_bulk(batch)
            inserted += len(batch)
        except Exception as e:
            print(f"  ✗ Final batch error: {e}")

    print(f"  ✓ Posts: {inserted} inserted, {skipped} skipped")


async def ingest_volume(path: str):
    print(f"→ Loading volume from {path}")
    import statistics
    rows_raw = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            # Handle both 'date' and 'created_datetime' column names
            date_val = row.get("date") or row.get("created_datetime") or ""
            count    = int(float(row.get("post_count", 0) or 0))
            if date_val:
                try:
                    d = datetime.strptime(date_val.strip()[:10], "%Y-%m-%d").date()
                    rows_raw.append((d, count))
                except Exception:
                    pass

    # Compute rolling 7-day mean/std/z-score
    WINDOW = 7
    count_inserted = 0
    for i, (d, pc) in enumerate(rows_raw):
        window_counts = [r[1] for r in rows_raw[max(0, i - WINDOW + 1): i + 1]]
        mean = statistics.mean(window_counts)
        std  = statistics.pstdev(window_counts) if len(window_counts) > 1 else 0.0
        z    = round((pc - mean) / std, 4) if std > 0 else 0.0
        try:
            await db.upsert_volume(
                date_val     = d,
                post_count   = pc,
                rolling_mean = round(mean, 4),
                rolling_std  = round(std, 4),
                z_score      = z,
            )
            count_inserted += 1
        except Exception as e:
            print(f"  ✗ {e}")
    print(f"  ✓ Volume: {count_inserted} rows")



async def ingest_domains(path: str):
    print(f"→ Loading distinctive domains from {path}")
    count = 0
    async with db.conn() as c:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    await c.execute("""
                        INSERT INTO top_distinctive_domains
                            (subreddit, domain, count, category, lift, p_domain_given_sub, p_domain_global)
                        VALUES ($1,$2,$3,$4,$5,$6,$7)
                        ON CONFLICT (subreddit, domain) DO NOTHING
                    """,
                        row["subreddit"], row["domain"],
                        int(row.get("count", 0)),
                        row.get("category", ""),
                        float(row.get("lift", 0)),
                        float(row.get("p_domain_given_sub", 0)),
                        float(row.get("p_domain_global", 0)),
                    )
                    count += 1
                except Exception as e:
                    print(f"  ✗ {e}")
    print(f"  ✓ Domains: {count} rows")


async def ingest_flow(path: str):
    print(f"→ Loading domain flow from {path}")
    count = 0
    async with db.conn() as c:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    await c.execute("""
                        INSERT INTO subreddit_domain_flow (subreddit, domain, post_count)
                        VALUES ($1,$2,$3)
                        ON CONFLICT (subreddit, domain) DO NOTHING
                    """, row["subreddit"], row["domain"], int(row.get("count", 0)))
                    count += 1
                except Exception as e:
                    print(f"  ✗ {e}")
    print(f"  ✓ Flow: {count} rows")


async def ingest_echo(path: str):
    print(f"→ Loading echo scores from {path}")
    count = 0
    async with db.conn() as c:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    await c.execute("""
                        INSERT INTO echo_chamber_scores (subreddit, echo_score)
                        VALUES ($1,$2)
                        ON CONFLICT (subreddit) DO UPDATE SET echo_score=$2
                    """, row["subreddit"], float(row.get("lift", 0)))
                    count += 1
                except Exception as e:
                    print(f"  ✗ {e}")
    print(f"  ✓ Echo: {count} rows")


# ── Main ──────────────────────────────────────────────────────

async def main(args):
    await db.init_pool()

    if args.posts:
        await ingest_posts(args.posts, args.embeddings or "")
    if args.volume:
        await ingest_volume(args.volume)
    if args.domains:
        await ingest_domains(args.domains)
    if args.flow:
        await ingest_flow(args.flow)
    if args.echo:
        await ingest_echo(args.echo)

    await db.close_pool()
    print("\n✓ Ingestion complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest CSV data into Neon")
    parser.add_argument("--posts",      help="Path to clean_posts.csv")
    parser.add_argument("--embeddings", help="Path to title_embeddings_v2.npy")
    parser.add_argument("--volume",     help="Path to daily_volume_v2.csv")
    parser.add_argument("--domains",    help="Path to clean_top_distinctive_domains.csv")
    parser.add_argument("--flow",       help="Path to subreddit_domain_flow_v2.csv")
    parser.add_argument("--echo",       help="Path to echo_chamber_scores.csv")
    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        sys.exit(1)

    asyncio.run(main(args))
