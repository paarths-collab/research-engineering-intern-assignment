"""
cluster_pipeline.py — Offline preprocessing for the 5-cluster narrative streamgraph.

Reads:
  - data/clean_posts.csv
  - data/title_embeddings_v2.npy

Produces (cached at first call):
  - data/posts_clustered.parquet

Cluster labels are assigned by KMeans on L2-normalised sentence embeddings.
The label names are heuristic but stable (fixed random_state=42).
"""

from pathlib import Path
import numpy as np
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────
# File lives at: backend/streamgraph2/data/cluster_pipeline.py
# parents[3] = project root  →  project_root/data/
_DATA_DIR    = Path(__file__).resolve().parents[3] / "data"
_PARQUET     = _DATA_DIR / "posts_clustered.parquet"

N_CLUSTERS = 5

# Human labels for each KMeans cluster (0-4).
# These are determined once after the first clustering run by looking at the
# top subreddits / title keywords in each group.
# With random_state=42 on this dataset the mapping is stable.
CLUSTER_LABELS: dict[int, str] = {
    0: "US Politics",
    1: "Geopolitics",
    2: "Economy",
    3: "Culture",
    4: "Technology",
}

# Ordered display list (used as streamgraph layer keys)
ORDERED_CLUSTERS = [CLUSTER_LABELS[i] for i in range(N_CLUSTERS)]


def _l2_normalize(emb: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(emb, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return emb / norms


def _kmeans_cosine(emb: np.ndarray, n_clusters: int, random_state: int = 42, max_iter: int = 40) -> np.ndarray:
    """Small NumPy k-means (cosine-like) to avoid heavyweight ML runtime deps."""
    rng = np.random.default_rng(random_state)
    n_samples = emb.shape[0]
    n_clusters = max(1, min(n_clusters, n_samples))

    initial = rng.choice(n_samples, size=n_clusters, replace=False)
    centroids = emb[initial].copy()
    labels = np.zeros(n_samples, dtype=np.int32)

    for _ in range(max_iter):
        sims = emb @ centroids.T
        new_labels = np.argmax(sims, axis=1).astype(np.int32)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels

        for cid in range(n_clusters):
            members = emb[labels == cid]
            if len(members) == 0:
                centroids[cid] = emb[rng.integers(0, n_samples)]
                continue
            centroid = members.mean(axis=0)
            norm = np.linalg.norm(centroid)
            centroids[cid] = centroid if norm == 0 else centroid / norm

    return labels


def build_clustered_data(force: bool = False) -> pd.DataFrame:
    """
    Run KMeans on pre-computed title embeddings, enrich clean_posts.csv,
    and persist to posts_clustered.parquet.

    Returns the enriched DataFrame.
    Re-uses cached parquet if it already exists unless force=True.
    """
    if _PARQUET.exists() and not force:
        return pd.read_parquet(_PARQUET)

    posts_path = _DATA_DIR / "clean_posts.csv"
    emb_path   = _DATA_DIR / "title_embeddings_v2.npy"

    if not posts_path.exists():
        raise FileNotFoundError(f"clean_posts.csv not found at {posts_path}")
    if not emb_path.exists():
        raise FileNotFoundError(f"title_embeddings_v2.npy not found at {emb_path}")

    df  = pd.read_csv(posts_path, parse_dates=["created_datetime"])
    emb = np.load(emb_path)

    if len(df) != len(emb):
        # Align on index — truncate to shorter length if mismatch
        n = min(len(df), len(emb))
        df  = df.iloc[:n].copy()
        emb = emb[:n]

    # L2-normalise so dot product approximates cosine similarity.
    emb_norm = _l2_normalize(emb)
    labels = _kmeans_cosine(emb_norm, n_clusters=N_CLUSTERS, random_state=42)

    df["cluster_id"]    = labels
    df["cluster_label"] = df["cluster_id"].map(CLUSTER_LABELS)
    df["date"]          = df["created_datetime"].dt.date

    # Persist only columns needed downstream
    keep = ["id", "date", "subreddit", "title", "domain", "cluster_id", "cluster_label"]
    result = df[keep].reset_index(drop=True)
    result.to_parquet(_PARQUET, index=False)
    return result


def get_clustered_df() -> pd.DataFrame:
    """
    Return the clustered posts DataFrame, building the parquet cache if needed.
    This is cheap after the first call (reads parquet in ~100ms).
    """
    return build_clustered_data()


if __name__ == "__main__":
    print("Building cluster assignments …")
    df = build_clustered_data(force=True)
    print(f"Done — {len(df)} posts across {df['cluster_label'].nunique()} clusters.\n")
    print(df.groupby("cluster_label").size().sort_values(ascending=False).to_string())
