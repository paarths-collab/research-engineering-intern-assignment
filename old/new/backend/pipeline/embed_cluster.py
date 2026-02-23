import pandas as pd
import numpy as np
from pathlib import Path

from sentence_transformers import SentenceTransformer
import umap
import hdbscan

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_PATH = BASE_DIR / "data" / "derived" / "preprocessed.parquet"
OUTPUT_PATH = BASE_DIR / "data" / "derived" / "semantic_points.parquet"

print("Loading preprocessed data...")
df = pd.read_parquet(INPUT_PATH)

# ----------------------------
# EMBEDDINGS
# ----------------------------
print("Loading embedding model...")
model = SentenceTransformer("all-MiniLM-L6-v2")

print("Generating embeddings...")
embeddings = model.encode(
    df["combined_text"].tolist(),
    batch_size=32,
    show_progress_bar=True
)

embeddings = np.array(embeddings)

# ----------------------------
# UMAP
# ----------------------------
print("Running UMAP...")
reducer = umap.UMAP(
    n_neighbors=15,
    min_dist=0.1,
    n_components=2,
    random_state=42
)

umap_coords = reducer.fit_transform(embeddings)

df["umap_x"] = umap_coords[:, 0]
df["umap_y"] = umap_coords[:, 1]

# ----------------------------
# HDBSCAN
# ----------------------------
print("Running HDBSCAN...")
clusterer = hdbscan.HDBSCAN(
    min_cluster_size=30,
    min_samples=5,
    cluster_selection_epsilon=0.05,
    metric="euclidean"
)

cluster_labels = clusterer.fit_predict(embeddings)
df["cluster_label"] = cluster_labels

df.to_parquet(OUTPUT_PATH, index=False)

print("Semantic layer complete.")