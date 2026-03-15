"""
hybrid_chatbot/router.py
------------------------
Keyword-based query router for SQL / embedding / hybrid paths.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import SQL_KEYWORDS, EMBED_KEYWORDS, HYBRID_KEYWORDS


@dataclass
class RouteDecision:
    route: str
    reason: str


class QueryRouter:
    def route(self, query: str) -> RouteDecision:
        q = query.lower()
        if _has_any(q, HYBRID_KEYWORDS):
            return RouteDecision(route="hybrid", reason="Hybrid keyword detected")
        if _has_any(q, SQL_KEYWORDS):
            return RouteDecision(route="sql", reason="SQL keyword detected")
        if _has_any(q, EMBED_KEYWORDS):
            return RouteDecision(route="embedding", reason="Embedding keyword detected")
        return RouteDecision(route="embedding", reason="Defaulting to embeddings")


def _has_any(text: str, needles: list[str]) -> bool:
    return any(n in text for n in needles)
