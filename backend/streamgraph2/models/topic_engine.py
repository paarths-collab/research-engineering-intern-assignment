"""
topic_engine.py — Lightweight narrative decomposition.

Rules:
  - Cluster ONLY spike_date posts (not ±1 window)
  - Store topic centroid as mean of member embeddings
  - Persist results into topic_results table
  - Optionally use Groq to refine cluster keywords/labels
"""

import json
import re
from collections import Counter
from datetime import date
from typing import Dict, List, Optional, Tuple

import numpy as np

from streamgraph2.data import db
from streamgraph2.data.config import BERTOPIC_MIN_TOPIC, GROQ_API_KEY, TOPIC_REFINER_MODEL

_STOP_WORDS = {
    "that", "this", "with", "from", "they", "have", "been", "more", "will", "just",
    "your", "about", "after", "there", "their", "would", "could", "should", "into", "over",
    "under", "between", "against", "while", "where", "which", "because", "across", "among",
}


def _parse_embedding(raw: str | None) -> np.ndarray | None:
    if not raw:
        return None
    try:
        vals = [float(x) for x in raw.strip("[]").split(",") if x.strip()]
        if not vals:
            return None
        return np.asarray(vals, dtype="float32")
    except Exception:
        return None


def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def _kmeans_cosine(embeddings: np.ndarray, n_clusters: int, random_state: int = 42, max_iter: int = 40) -> np.ndarray:
    rng = np.random.default_rng(random_state)
    n_samples = embeddings.shape[0]
    n_clusters = max(1, min(n_clusters, n_samples))

    indices = rng.choice(n_samples, size=n_clusters, replace=False)
    centroids = embeddings[indices].copy()
    labels = np.zeros(n_samples, dtype=np.int32)

    for _ in range(max_iter):
        sims = embeddings @ centroids.T
        new_labels = np.argmax(sims, axis=1).astype(np.int32)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels

        for cid in range(n_clusters):
            members = embeddings[labels == cid]
            if len(members) == 0:
                centroids[cid] = embeddings[rng.integers(0, n_samples)]
                continue
            centroid = members.mean(axis=0)
            norm = np.linalg.norm(centroid)
            centroids[cid] = centroid if norm == 0 else centroid / norm

    return labels


def _extract_keywords(texts: List[str], top_k: int = 8) -> List[str]:
    words = re.findall(r"\b[a-zA-Z]{4,}\b", " ".join(texts).lower())
    counts = Counter(w for w in words if w not in _STOP_WORDS)
    return [w for w, _ in counts.most_common(top_k)]


def _groq_refine_keywords(texts: List[str], fallback: List[str]) -> Tuple[str | None, List[str]]:
    if not GROQ_API_KEY or not texts:
        return None, fallback

    try:
        from groq import Groq

        client = Groq(api_key=GROQ_API_KEY)
        sample = "\n".join(f"- {t}" for t in texts[:20])
        prompt = (
            "Given the following post titles from one detected cluster, return JSON with a short label and up to 8 keywords. "
            "Return only JSON with this schema: {\"label\": string, \"keywords\": string[]}.\n\n"
            f"Titles:\n{sample}"
        )
        completion = client.chat.completions.create(
            model=TOPIC_REFINER_MODEL.replace("groq/", ""),
            temperature=0,
            messages=[
                {"role": "system", "content": "You extract concise topic labels and keywords."},
                {"role": "user", "content": prompt},
            ],
        )
        content = completion.choices[0].message.content or ""
        parsed = json.loads(content)
        label = str(parsed.get("label", "")).strip() or None
        raw_keywords = parsed.get("keywords", [])
        keywords = [str(k).strip().lower() for k in raw_keywords if str(k).strip()]
        if keywords:
            return label, keywords[:8]
    except Exception:
        pass

    return None, fallback


async def run_topic_modeling(job_id: str, spike_date: date, min_topic_size_override: Optional[int] = None) -> List[Dict]:
    """
    1. Load spike_date posts from DB
    2. Run lightweight clustering
    3. Store results
    4. Return list of topic dicts
    """
    print(f"  [Topics] Loading posts for {spike_date}")
    rows = await db.get_posts_for_date(spike_date)

    if not rows:
        print("  [Topics] No posts found for spike date")
        return []

    records = []
    for r in rows:
        emb = _parse_embedding(r.get("embedding"))
        title = str(r.get("title", "")).strip()
        if emb is None or not title:
            continue
        records.append((title, emb))

    if not records:
        print("  [Topics] No valid title+embedding rows found")
        return []

    titles = [title for title, _ in records]
    embeddings = np.vstack([emb for _, emb in records]).astype("float32")
    embeddings = _normalize_rows(embeddings)

    active_min_topic_size = min_topic_size_override if min_topic_size_override is not None else BERTOPIC_MIN_TOPIC

    # Keep the same high-level behavior: up to 3 topic clusters.
    n_clusters = min(3, max(1, len(titles) // max(active_min_topic_size, 1)))
    if n_clusters == 1 and len(titles) >= 15:
        n_clusters = 2

    print(f"  [Topics] Running lightweight clustering on {len(titles)} posts (k={n_clusters}, min_topic_size={active_min_topic_size})")
    cluster_ids = _kmeans_cosine(embeddings, n_clusters=n_clusters)

    total      = len(titles)
    results    = []

    for tid in sorted(set(cluster_ids.tolist())):
        member_indices = [i for i, t in enumerate(cluster_ids) if int(t) == int(tid)]
        size = len(member_indices)
        if size == 0:
            continue
        pct  = round((size / total) * 100, 2)

        representative_posts = [titles[i] for i in member_indices[:50]]
        keywords = _extract_keywords(representative_posts)
        label, refined_keywords = _groq_refine_keywords(representative_posts, keywords)
        if refined_keywords:
            keywords = refined_keywords

        # Centroid: mean of member embeddings (de-normalized representation not required downstream)
        centroid = embeddings[member_indices].mean(axis=0).tolist()

        await db.save_topic(
            job_id      = job_id,
            topic_id    = int(tid),
            size        = size,
            size_percent= pct,
            keywords    = keywords,
            centroid    = centroid,
        )

        results.append({
            "topic_id"            : int(tid),
            "size"                : size,
            "size_percent"        : pct,
            "keywords"            : keywords,
            "label"               : label,
            "centroid"            : centroid,
            "representative_posts": representative_posts,
        })

    print(f"  [Topics] {len(results)} topics stored")
    return results
