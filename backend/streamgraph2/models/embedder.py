"""
embedder.py — Singleton sentence-transformer embedder.
Loaded once, reused everywhere. Avoids redundant model loads.
"""

from sentence_transformers import SentenceTransformer
from streamgraph2.data.config import EMBEDDING_MODEL

_model: SentenceTransformer = None


def get_embedder() -> SentenceTransformer:
    global _model
    if _model is None:
        print(f"  Loading embedding model: {EMBEDDING_MODEL}")
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def embed(texts: list) -> list:
    """Embed a list of strings. Returns list of float lists."""
    model = get_embedder()
    return model.encode(texts, show_progress_bar=False).tolist()
