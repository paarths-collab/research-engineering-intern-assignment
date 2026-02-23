import duckdb
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from pathlib import Path
from sklearn.metrics.pairwise import cosine_similarity

# === PATHS ===
# BASE_DIR resolves to: .../mostly/
BASE_DIR = Path(__file__).parent.parent
DB_PATH   = BASE_DIR / "data" / "analysis_v2.db"
EMB_PATH  = BASE_DIR / "data" / "title_embeddings_v2.npy"
CSV_PATH  = BASE_DIR / "data" / "clean_with_clusters_v2.csv"

# === GLOBAL SINGLETONS ===
CONN       = None
EMBEDDINGS = None
MODEL      = None
POSTS_DF   = None


def get_db_connection():
    """Lazy singleton DuckDB connection."""
    global CONN
    if CONN is None:
        print(f"🦆 Connecting to DuckDB at {DB_PATH}...")
        CONN = duckdb.connect(str(DB_PATH), read_only=True)
    return CONN


def get_vector_store():
    """Lazy-load embeddings, sentence model, and posts dataframe."""
    global EMBEDDINGS, MODEL, POSTS_DF
    if EMBEDDINGS is None:
        print(f"🧠 Loading embeddings from {EMB_PATH}...")
        EMBEDDINGS = np.load(str(EMB_PATH))

        print("🤖 Loading SentenceTransformer model...")
        MODEL = SentenceTransformer("all-MiniLM-L6-v2")

        print(f"📄 Loading posts CSV from {CSV_PATH}...")
        POSTS_DF = pd.read_csv(str(CSV_PATH))

    return EMBEDDINGS, MODEL, POSTS_DF


def semantic_search(query: str, top_k: int = 5):
    """Find posts semantically similar to the query using the CSV index."""
    embeddings, model, posts_df = get_vector_store()

    query_vec = model.encode([query])
    scores = cosine_similarity(query_vec, embeddings)[0]
    top_indices = scores.argsort()[-top_k:][::-1]

    results = []
    for idx in top_indices:
        row = posts_df.iloc[idx]
        results.append({
            "title":     str(row.get("title", "")),
            "subreddit": str(row.get("subreddit", "")),
            "date":      str(row.get("created_datetime", "")),
            "score":     float(scores[idx]),
        })

    return results