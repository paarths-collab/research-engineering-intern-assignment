"""
hybrid_chatbot/vector_store.py
------------------------------
FAISS-backed vector index for narrative text chunks.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Optional

import numpy as np

from .config import (
    DATA_DIR,
    VECTOR_INDEX_PATH,
    VECTOR_META_PATH,
    EMBED_MODEL_NAME,
    CHUNK_MIN_TOKENS,
    CHUNK_MAX_TOKENS,
)

logger = logging.getLogger("hybrid_chatbot.vector")


@dataclass
class VectorDoc:
    text: str
    metadata: dict


class VectorIndex:
    def __init__(self, index_path: Path = VECTOR_INDEX_PATH, meta_path: Path = VECTOR_META_PATH):
        self.index_path = index_path
        self.meta_path = meta_path
        self._index = None
        self._meta: list[dict] = []
        self._embedder = None

    def load(self) -> None:
        if not self.index_path.exists() or not self.meta_path.exists():
            raise FileNotFoundError(
                f"Vector index missing. Expected {self.index_path} and {self.meta_path}."
            )
        import faiss  # local import for optional dependency

        self._index = faiss.read_index(str(self.index_path))
        self._meta = [json.loads(line) for line in self.meta_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        logger.info("Vector index loaded: %s docs", len(self._meta))

    def _load_embedder(self):
        from sentence_transformers import SentenceTransformer
        # Runtime should stay offline-friendly; embeddings are expected to be prepared ahead of time.
        return SentenceTransformer(EMBED_MODEL_NAME, local_files_only=True)

    def search(self, query: str, top_k: int = 6, filters: Optional[dict] = None) -> list[dict]:
        if self._index is None:
            self.load()
        if self._embedder is None:
            try:
                self._embedder = self._load_embedder()
            except Exception as exc:
                logger.warning("Vector embedder unavailable; skipping vector search: %s", exc)
                return []

        q_emb = self._embedder.encode([query], normalize_embeddings=True)
        q_emb = np.asarray(q_emb, dtype="float32")

        import faiss

        k = max(top_k * 5, top_k)
        scores, indices = self._index.search(q_emb, k)

        results: list[dict] = []
        for idx, score in zip(indices[0], scores[0]):
            if idx < 0:
                continue
            meta = self._meta[idx]
            if filters and not _match_filters(meta, filters):
                continue
            results.append({
                "text": meta.get("text", ""),
                "score": float(score),
                "metadata": meta,
            })
            if len(results) >= top_k:
                break

        if filters and not results:
            # Fallback: return unfiltered results if filters are too restrictive
            return self.search(query, top_k=top_k, filters=None)

        return results


# ── Index Builder ───────────────────────────────────────────────────────────-

def build_index(index_path: Path = VECTOR_INDEX_PATH, meta_path: Path = VECTOR_META_PATH) -> None:
    import faiss
    from sentence_transformers import SentenceTransformer

    docs = list(_collect_documents())
    if not docs:
        raise RuntimeError("No documents found to embed.")

    texts = [d.text for d in docs]
    embedder = SentenceTransformer(EMBED_MODEL_NAME)
    embeddings = embedder.encode(texts, batch_size=64, show_progress_bar=True, normalize_embeddings=True)
    embeddings = np.asarray(embeddings, dtype="float32")

    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)

    index_path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_path))

    meta_path.write_text(
        "\n".join(json.dumps({"text": d.text, **d.metadata}, ensure_ascii=False) for d in docs),
        encoding="utf-8",
    )

    logger.info("Vector index built: %s docs", len(docs))


def _collect_documents() -> Iterable[VectorDoc]:
    yield from _docs_from_narratives()
    yield from _docs_from_graph_edges()
    yield from _docs_from_posts()


def _docs_from_posts() -> Iterable[VectorDoc]:
    path = DATA_DIR / "clean_with_clusters_v2.csv"
    if not path.exists():
        return
    import pandas as pd

    df = pd.read_csv(path)
    if df.empty:
        return

    grouped = df.groupby("subreddit")
    for subreddit, group in grouped:
        titles = []
        dates = []
        domains = []
        for _, row in group.iterrows():
            title = str(row.get("title", "")).strip()
            if not title:
                continue
            date_val = str(row.get("created_datetime", ""))
            dates.append(date_val)
            domains.append(str(row.get("domain", "")))
            titles.append(f"{date_val} | r/{subreddit} | {title}")

        for chunk in _chunk_lines(titles):
            meta = {
                "source": "clean_with_clusters_v2",
                "narrative_id": None,
                "subreddit": subreddit,
                "domain": _mode(domains),
                "date": _first_non_empty(dates),
            }
            yield VectorDoc(text=chunk, metadata=meta)


def _docs_from_graph_edges() -> Iterable[VectorDoc]:
    path = DATA_DIR / "graph_edge_intelligence_table.csv"
    if not path.exists():
        return
    import pandas as pd

    df = pd.read_csv(path)
    if df.empty:
        return

    grouped = df.groupby("narrative_id")
    for narrative_id, group in grouped:
        titles = []
        dates = []
        domains = []
        subreddits = []
        for _, row in group.iterrows():
            title = str(row.get("title", "")).strip()
            if not title:
                continue
            date_val = str(row.get("created_datetime", ""))
            subreddit = str(row.get("subreddit", ""))
            domain = str(row.get("domain", ""))
            titles.append(f"{date_val} | r/{subreddit} | {title}")
            dates.append(date_val)
            domains.append(domain)
            subreddits.append(subreddit)

        for chunk in _chunk_lines(titles):
            meta = {
                "source": "graph_edge_intelligence_table",
                "narrative_id": str(narrative_id),
                "subreddit": _mode(subreddits),
                "domain": _mode(domains),
                "date": _first_non_empty(dates),
            }
            yield VectorDoc(text=chunk, metadata=meta)


def _docs_from_narratives() -> Iterable[VectorDoc]:
    reg_path = DATA_DIR / "narrative_registry.csv"
    intel_path = DATA_DIR / "narrative_intelligence_summary.csv"
    topic_path = DATA_DIR / "narrative_topic_mapping.csv"

    if not reg_path.exists():
        return

    import pandas as pd

    reg = pd.read_csv(reg_path)
    intel = pd.read_csv(intel_path) if intel_path.exists() else pd.DataFrame()
    topic = pd.read_csv(topic_path) if topic_path.exists() else pd.DataFrame()

    intel_map = {
        str(r["narrative_id"]): r
        for r in intel.to_dict(orient="records")
    } if not intel.empty else {}

    topic_map = {}
    if not topic.empty:
        for r in topic.to_dict(orient="records"):
            topic_map.setdefault(str(r["narrative_id"]), []).append(str(r.get("topic_label", "")))

    for row in reg.to_dict(orient="records"):
        narrative_id = str(row.get("narrative_id", ""))
        rep_title = str(row.get("representative_title", ""))
        primary_domain = str(row.get("primary_domain", ""))
        first_seen = str(row.get("first_seen", ""))
        total_posts = str(row.get("total_posts", ""))
        unique_subs = str(row.get("unique_subreddits", ""))

        intel_row = intel_map.get(narrative_id, {})
        spread_strength = str(intel_row.get("spread_strength", ""))
        last_seen = str(intel_row.get("last_seen", ""))

        topics = ", ".join(t for t in topic_map.get(narrative_id, []) if t)

        text_parts = [
            f"Narrative {narrative_id}.",
            f"Representative title: {rep_title}.",
            f"Primary domain: {primary_domain}.",
            f"First seen: {first_seen}.",
        ]
        if last_seen:
            text_parts.append(f"Last seen: {last_seen}.")
        if total_posts:
            text_parts.append(f"Total posts: {total_posts}.")
        if unique_subs:
            text_parts.append(f"Unique subreddits: {unique_subs}.")
        if spread_strength:
            text_parts.append(f"Spread strength: {spread_strength}.")
        if topics:
            text_parts.append(f"Topics: {topics}.")

        text = " ".join(text_parts).strip()
        if not text:
            continue

        meta = {
            "source": "narrative_registry",
            "narrative_id": narrative_id,
            "subreddit": None,
            "domain": primary_domain or None,
            "date": first_seen or None,
        }
        yield VectorDoc(text=text, metadata=meta)


# ── Chunking helpers ─────────────────────────────────────────────────────────

def _chunk_lines(lines: list[str]) -> Iterable[str]:
    current = []
    count = 0
    for line in lines:
        tokens = len(line.split())
        if count + tokens > CHUNK_MAX_TOKENS and count >= CHUNK_MIN_TOKENS:
            yield "\n".join(current)
            current = []
            count = 0
        current.append(line)
        count += tokens
    if current:
        yield "\n".join(current)


def _mode(values: list[str]) -> Optional[str]:
    if not values:
        return None
    counts = {}
    for v in values:
        if not v:
            continue
        counts[v] = counts.get(v, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


def _first_non_empty(values: list[str]) -> Optional[str]:
    for v in values:
        if v:
            return v
    return None


def _match_filters(meta: dict, filters: dict) -> bool:
    for key, value in filters.items():
        if key == "date_range":
            if not _date_in_range(meta.get("date"), value):
                return False
            continue
        if value is None:
            continue
        meta_val = meta.get(key)
        if meta_val is None:
            return False
        if isinstance(value, str):
            if str(meta_val) != value:
                return False
        elif isinstance(value, (list, tuple, set)):
            if str(meta_val) not in {str(v) for v in value}:
                return False
        else:
            if meta_val != value:
                return False
    return True


def _date_in_range(value: Optional[str], date_range: tuple[str, str]) -> bool:
    if not value:
        return False
    try:
        date_str = str(value).split(" ")[0].split("T")[0]
        val = date.fromisoformat(date_str)
    except Exception:
        return False
    try:
        start = date.fromisoformat(date_range[0])
        end = date.fromisoformat(date_range[1])
    except Exception:
        return False
    return start <= val <= end
