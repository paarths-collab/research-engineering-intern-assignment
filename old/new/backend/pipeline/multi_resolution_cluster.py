import pandas as pd
from sentence_transformers import SentenceTransformer
import umap
import hdbscan

df = pd.read_parquet("data/derived/preprocessed.parquet")

model = SentenceTransformer("all-MiniLM-L6-v2")
embeddings = model.encode(df["combined_text"].tolist(), batch_size=64, show_progress_bar=True)

reducer = umap.UMAP(n_neighbors=15, n_components=5, min_dist=0.0, metric="cosine")
emb = reducer.fit_transform(embeddings)

configs = [
    (15,3),
    (20,5),
    (30,5),
    (40,10),
    (60,10),
    (80,15),
]

results = []

for min_cluster_size, min_samples in configs:
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        cluster_selection_epsilon=0.02
    )
    labels = clusterer.fit_predict(emb)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    noise = (labels == -1).sum()

    results.append((min_cluster_size, min_samples, n_clusters, noise))

print("\nRESULTS:")
for r in results:
    print(f"min_cluster={r[0]:3d}  min_samples={r[1]:2d}  clusters={r[2]:2d}  noise={r[3]}")
