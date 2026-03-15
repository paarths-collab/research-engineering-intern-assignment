"""Build the FAISS vector index for the hybrid chatbot."""

from __future__ import annotations

import sys
from pathlib import Path


def _load_builder():
    try:
        from hybrid_chatbot.vector_store import build_index  # type: ignore
        return build_index
    except ImportError:
        backend_dir = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(backend_dir))
        from hybrid_chatbot.vector_store import build_index  # type: ignore
        return build_index


if __name__ == "__main__":
    _load_builder()()
