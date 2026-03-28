"""
embedder.py — Lightweight deterministic text embedder.
No external model downloads; suitable for lean deployment.
"""

import hashlib
import re
from typing import Callable

import numpy as np

from streamgraph2.data.config import EMBEDDING_MODEL

_model: Callable[[str], np.ndarray] | None = None
_DIM = 384


def _hash_embed(text: str) -> np.ndarray:
    vec = np.zeros(_DIM, dtype="float32")
    tokens = re.findall(r"[a-z0-9]+", str(text).lower())
    for tok in tokens:
        if len(tok) < 2:
            continue
        idx = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16) % _DIM
        vec[idx] += 1.0
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


def get_embedder() -> Callable[[str], np.ndarray]:
    global _model
    if _model is None:
        print(f"  Loading embedding model: {EMBEDDING_MODEL}")
        _model = _hash_embed
    return _model


def embed(texts: list) -> list:
    """Embed a list of strings. Returns list of float lists."""
    model = get_embedder()
    return [model(t).tolist() for t in texts]
