import json
import re
import os
import sys
import pandas as pd
from datetime import datetime
import emoji
from tqdm import tqdm

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import database

# ----------------------------------
# CLEAN TEXT FUNCTION
# ----------------------------------

def clean_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("<!-- SC_ON -->", "").replace("<!-- SC_OFF -->", "")
    text = emoji.demojize(text)
    text = re.sub(r"http\S+", "<URL>", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


# ----------------------------------
# STREAM JSONL
# ----------------------------------

def stream_jsonl(path):
    # Adjust path if called from ingestion/ subdirectory
    if not os.path.exists(path):
        root_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)
        if os.path.exists(root_path):
            path = root_path
            
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                yield json.loads(line)
            except:
                continue


# ----------------------------------
# MAIN PREPROCESS FUNCTION
# ----------------------------------

def run_preprocessing():
    records = []

    print(f"Processing file: {config.RAW_DATA_PATH}")

    for raw in tqdm(stream_jsonl(config.RAW_DATA_PATH)):
        data = raw.get("data", raw)

        ts = data.get("created_utc")
        if not ts:
            continue

        # Temporal alignment logic
        timestamp = pd.to_datetime(ts, unit="s", utc=True)

        title = data.get("title", "")
        body = data.get("selftext", "")
        full_text = f"{title} {body}"

        cleaned = clean_text(full_text)

        if len(cleaned) < 30:
            continue

        record = {
            "id": data.get("id"),
            "dataset": config.DATASET_NAME,
            "author": data.get("author", "unknown"),
            "subreddit": data.get("subreddit", ""),
            "timestamp": timestamp,
            "day": timestamp.date(),
            "week": timestamp.to_period("W").start_time,
            "month": timestamp.to_period("M").start_time,
            "hour": timestamp.floor("h"),
            "clean_text": cleaned,
            "score": data.get("score", 0),
            "upvote_ratio": data.get("upvote_ratio", 0.0)
        }

        records.append(record)

    df = pd.DataFrame(records)

    print(f"Total valid posts: {len(df)}")

    if df.empty:
        print("No valid records found.")
        return

    conn = database.get_connection()

    # Register DataFrame as temporary table
    conn.register("temp_df", df)

    # Simple approach for table creation/insertion
    # If posts table doesn't exist, create it from df
    conn.execute("CREATE TABLE IF NOT EXISTS posts AS SELECT * FROM temp_df WHERE 1=0")
    
    # Check if we need to add columns (in case table existed with fewer columns)
    existing_cols = conn.execute("PRAGMA table_info('posts')").fetchdf()['name'].tolist()
    for col in df.columns:
        if col not in existing_cols:
            dtype = "TEXT"
            if "timestamp" in col or "day" in col or "week" in col or "month" in col or "hour" in col:
                dtype = "TIMESTAMP"
            elif "score" in col:
                dtype = "INTEGER"
            elif "ratio" in col:
                dtype = "DOUBLE"
            conn.execute(f"ALTER TABLE posts ADD COLUMN {col} {dtype}")

    # Insert data with explicit columns
    cols = ", ".join(df.columns)
    conn.execute(f"INSERT INTO posts ({cols}) SELECT {cols} FROM temp_df")

    conn.close()
    print("Data inserted successfully.")

if __name__ == "__main__":
    run_preprocessing()
