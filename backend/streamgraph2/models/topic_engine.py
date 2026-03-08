"""
topic_engine.py — Narrative decomposition using BERTopic.

Rules:
  - Cluster ONLY spike_date posts (not ±1 window)
  - Store topic centroid as mean of member embeddings
  - Skip noise topic (-1)
  - Persist results into topic_results table
"""

import numpy as np
from datetime import date
from typing import List, Dict

from streamgraph2.data import db
from streamgraph2.data.config import BERTOPIC_MIN_TOPIC
from streamgraph2.models.embedder import get_embedder


async def run_topic_modeling(job_id: str, spike_date: date, min_topic_size_override: int = None) -> List[Dict]:
    """
    1. Load spike_date posts from DB
    2. Run BERTopic
    3. Store results
    4. Return list of topic dicts
    """
    try:
        from bertopic import BERTopic
    except ImportError:
        raise RuntimeError("Install bertopic: pip install bertopic")

    print(f"  [Topics] Loading posts for {spike_date}")
    rows = await db.get_posts_for_date(spike_date)

    if not rows:
        print("  [Topics] No posts found for spike date")
        return []

    titles    = [r["title"] for r in rows]
    raw_embs  = [r["embedding"] for r in rows]

    # Parse embeddings from pgvector string
    embeddings = np.array([
        [float(x) for x in e.strip("[]").split(",")]
        for e in raw_embs
        if e is not None
    ])

    # Use precomputed embeddings so BERTopic doesn't re-embed
    embedder = get_embedder()

    from hdbscan import HDBSCAN
    from sklearn.feature_extraction.text import CountVectorizer

    hdbscan_model = HDBSCAN(
        min_cluster_size=20,
        min_samples=10,
        metric="euclidean",
        prediction_data=True
    )

    vectorizer_model = CountVectorizer(stop_words="english", min_df=2)

    # Enforce exactly 3 clusters, but let the min_topic_size adapt dynamically 
    # if the supervisor agent detects garbage fragmentation.
    active_min_topic_size = min_topic_size_override if min_topic_size_override is not None else BERTOPIC_MIN_TOPIC

    print(f"  [Topics] Running BERTopic on {len(titles)} posts (min_topic_size={active_min_topic_size})")
    topic_model = BERTopic(
        embedding_model         = embedder,
        hdbscan_model           = hdbscan_model,
        vectorizer_model        = vectorizer_model,
        min_topic_size          = active_min_topic_size,
        nr_topics               = 3, 
        calculate_probabilities = False,
        verbose                 = False,
    )

    topics, _ = topic_model.fit_transform(titles, embeddings)

    # Aggregate results
    topic_info = topic_model.get_topic_info()
    total      = len(titles)
    results    = []

    for _, row in topic_info.iterrows():
        tid = row["Topic"]
        if tid == -1:   # noise — skip
            continue

        size = int(row["Count"])
        pct  = round((size / total) * 100, 2)

        # Keywords: list of (word, score) tuples
        kw_raw  = topic_model.get_topic(tid)
        keywords = [w for w, _ in kw_raw] if kw_raw else []

        # Representative docs
        rep_docs = topic_model.get_representative_docs(tid)
        representative_posts = rep_docs[:50] if rep_docs else []

        # Centroid: mean of member embeddings
        member_indices = [i for i, t in enumerate(topics) if t == tid]
        centroid = embeddings[member_indices].mean(axis=0).tolist()

        await db.save_topic(
            job_id      = job_id,
            topic_id    = tid,
            size        = size,
            size_percent= pct,
            keywords    = keywords,
            centroid    = centroid,
        )

        results.append({
            "topic_id"            : tid,
            "size"                : size,
            "size_percent"        : pct,
            "keywords"            : keywords,
            "centroid"            : centroid,
            "representative_posts": representative_posts,
        })

    print(f"  [Topics] {len(results)} topics stored")
    return results
