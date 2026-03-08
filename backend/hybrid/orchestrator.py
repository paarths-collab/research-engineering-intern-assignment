"""
hybrid/orchestrator.py
-----------------------
Orchestrator Agent — classification only, no tools, single LLM call.

Fix 2: Uses llm.with_structured_output(RouteDecision) instead of
        manual JSON parsing. Routing is now schema-enforced and deterministic.
"""

import logging
from typing import Literal

from pydantic import BaseModel
from langchain_groq import ChatGroq
from langchain.schema import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


# ── Pydantic schema enforced on orchestrator output ────────────────────────────
class RouteDecision(BaseModel):
    route:  Literal["sql_only", "vector_only", "hybrid"]
    reason: str


_SYSTEM_PROMPT = """You are a routing controller for a political Reddit analysis system.

Your ONLY job is to classify the user query. Do NOT answer it. Do NOT generate data.

ROUTING RULES:
- sql_only    : counts, rankings, scores, dates, metrics, specific authors or
                subreddits, amplification, volume, echo chamber, ideological distance.
- vector_only : themes, narratives, framing, ideology, sentiment, rhetoric —
                with NO numeric requirement.
- hybrid      : requires BOTH numeric analysis AND thematic/narrative analysis.

Return the route and a one-sentence reason."""


class OrchestratorAgent:
    """
    Single LLM call with structured output enforcement.
    No agent loop. No tools. max_iterations=1 by design.
    Falls back to 'hybrid' on any error (safe default).
    """

    def __init__(self, llm: ChatGroq):
        # Bind structured output schema directly to the LLM
        self._structured_llm = llm.with_structured_output(RouteDecision)

    def classify(self, user_query: str) -> RouteDecision:
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=f'Classify this query: "{user_query}"'),
        ]
        try:
            decision: RouteDecision = self._structured_llm.invoke(messages)
            logger.info(f"[Orchestrator] route={decision.route} | {decision.reason}")
            return decision
        except Exception as exc:
            logger.warning(f"[Orchestrator] Structured output failed ({exc}), defaulting to hybrid.")
            return RouteDecision(route="hybrid", reason="fallback: structured output parse error")
