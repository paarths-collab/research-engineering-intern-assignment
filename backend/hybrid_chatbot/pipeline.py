"""
hybrid_chatbot/pipeline.py
-------------------------
Dataset-grounded chatbot pipeline with optional DuckDuckGo web search.
"""

from __future__ import annotations

import json
import logging
import re
import time

from .dataset_context import DatasetContextStore
from .llm_client import LLMClient
from .web_search import WebSearchClient

logger = logging.getLogger("hybrid_chatbot.pipeline")

PROJECT_CONTEXT = """
Platform name: NarrativeSignal (intelligence analysis platform).
Primary purpose: analyze how narratives and discussions spread across online communities.
Core capabilities:
- community relationship and influence analysis
- narrative evolution over time (timeline / stream analysis)
- geographic spread of discussion (globe view)
- cross-community network exploration
- post/content analysis for context behind emerging narratives
Key modules:
- Polar Analysis: media ecosystem and community source patterns
- Narrative Ecosystem: network relationships and narrative pathways
- Streamgraph: temporal trend and spike behavior
- Globe: geospatial incident and discussion spread
- Chatbot: guided analysis and interpretation assistant
Typical intelligence datasets include:
- narrative_diffusion_table
- subreddit_domain_flow_v2
- daily_volume_v2
- narrative_registry
- author_influence_profile
- echo_chamber_scores
""".strip()

CHAT_SYSTEM_PROMPT = (
    "You are the dedicated assistant for the NarrativeSignal platform. "
    "Always answer in project context, not as a generic AI chatbot. "
    "Never say your purpose is just general conversation. "
    "Ground answers in provided dataset evidence first. "
    "If web evidence is provided, integrate it and clearly separate dataset findings vs web findings."
)

SENTIMENT_SYSTEM_PROMPT = (
    "You are a strict sentiment classifier for policy/news QA outputs. "
    "Return only valid JSON with keys: sentiment_label, sentiment_score, confidence, rationale. "
    "sentiment_label must be one of: positive, negative, neutral, mixed. "
    "sentiment_score must be a float from -1.0 to 1.0. "
    "confidence must be a float from 0.0 to 1.0. "
    "rationale must be one concise sentence."
)


class ChatPipeline:
    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.dataset_store = DatasetContextStore()
        self.web = WebSearchClient()

    def run(self, query: str, web_search: bool = False, dataset_top_k: int = 8) -> dict:
        timings: dict[str, float] = {}
        t_start = time.perf_counter()

        # Dataset grounding (always on)
        t0 = time.perf_counter()
        dataset_hits = self.dataset_store.search(query, top_k=dataset_top_k)
        timings["dataset"] = round(time.perf_counter() - t0, 3)

        # Optional web search + scrape
        web_hits: list[dict] = []
        if web_search:
            t0 = time.perf_counter()
            web_hits = self.web.search_and_scrape(query, max_results=4)
            timings["web_search"] = round(time.perf_counter() - t0, 3)

        # LLM synthesis
        t0 = time.perf_counter()
        try:
            user_prompt = _build_chat_prompt(
                query=query,
                dataset_summary=self.dataset_store.summary(),
                dataset_hits=dataset_hits,
                web_hits=web_hits,
                web_search=web_search,
            )
            max_tokens = 900 if web_search else 500
            answer, llm_time = self.llm.generate(CHAT_SYSTEM_PROMPT, user_prompt, max_tokens=max_tokens)
        except Exception as exc:
            logger.warning("LLM unavailable: %s", exc)
            answer = _fallback_answer(query, dataset_hits, web_hits, web_search)
            llm_time = 0.0
        timings["llm"] = round(llm_time, 3)
        timings["route"] = round(time.perf_counter() - t0 - llm_time, 3)

        # Sentiment
        sentiment, sentiment_time = _analyze_sentiment(self.llm, query, answer)
        timings["sentiment"] = round(sentiment_time, 3)
        timings["total"] = round(time.perf_counter() - t_start, 3)

        route = "chat_web" if web_search else "chat_dataset"
        logger.info("Route=%s dataset_hits=%s web_hits=%s", route, len(dataset_hits), len(web_hits))

        return {
            "answer": answer,
            "sentiment": sentiment,
            "route": route,
            "timing": timings,
            "dataset_chunks": dataset_hits,
            "web_articles": web_hits,
        }


def _build_chat_prompt(
    query: str,
    dataset_summary: str,
    dataset_hits: list[dict],
    web_hits: list[dict],
    web_search: bool,
) -> str:
    dataset_context = _format_dataset_hits(dataset_hits)
    web_context = _format_web_hits(web_hits) if web_search else "Web search not requested."
    web_mode = "enabled" if web_search else "disabled"

    return (
        f"PROJECT CONTEXT:\n{PROJECT_CONTEXT}\n\n"
        f"DATASET SUMMARY:\n{dataset_summary}\n\n"
        f"USER QUESTION:\n{query}\n\n"
        f"WEB SEARCH MODE: {web_mode}\n\n"
        f"DATASET EVIDENCE:\n{dataset_context}\n\n"
        f"WEB EVIDENCE:\n{web_context}\n\n"
        "INSTRUCTIONS:\n"
        "- Answer as NarrativeSignal assistant and stay project-specific.\n"
        "- Use dataset evidence as the primary source.\n"
        "- If web evidence is available, add a separate 'Web context' section with concrete takeaways.\n"
        "- If evidence is weak, clearly state limitations.\n"
        "- For web mode enabled, provide a deeper 2-part answer:\n"
        "  1) Dataset-grounded analysis\n"
        "  2) Web context and implications\n"
        "- Keep claims tied to provided evidence only.\n"
    )


def _format_dataset_hits(hits: list[dict]) -> str:
    if not hits:
        return "No matching dataset snippets found."
    lines = []
    for i, h in enumerate(hits[:10], start=1):
        src = h.get("source", "dataset")
        score = h.get("score", 0.0)
        text = str(h.get("text", "")).strip()
        lines.append(f"[dataset:{i}] source={src} score={score}: {text}")
    return "\n".join(lines)


def _format_web_hits(hits: list[dict]) -> str:
    if not hits:
        return "No web articles retrieved."
    lines = []
    for i, h in enumerate(hits[:5], start=1):
        title = str(h.get("title", "")).strip()
        source = str(h.get("source", "")).strip()
        url = str(h.get("url", "")).strip()
        snippet = str(h.get("snippet", "")).strip()
        content = str(h.get("content", "")).strip()[:800]
        lines.append(
            f"[web:{i}] {title} ({source})\nURL: {url}\nSnippet: {snippet}\nExtract: {content}"
        )
    return "\n\n".join(lines)


def _fallback_answer(query: str, dataset_hits: list[dict], web_hits: list[dict], web_search: bool) -> str:
    lines = [
        "I could not reach the language model, so this is a deterministic evidence summary.",
        f"Question: {query}",
    ]
    if dataset_hits:
        lines.append(f"Dataset matches: {len(dataset_hits)}")
        for h in dataset_hits[:3]:
            lines.append(f"- [{h.get('source')}] {h.get('text')}")
    else:
        lines.append("Dataset matches: none")
    if web_search:
        if web_hits:
            lines.append(f"Web articles retrieved: {len(web_hits)}")
            for w in web_hits[:2]:
                lines.append(f"- [{w.get('source')}] {w.get('title')} ({w.get('url')})")
        else:
            lines.append("Web articles retrieved: none")
    return "\n".join(lines)


def _analyze_sentiment(llm: LLMClient, query: str, answer: str) -> tuple[dict, float]:
    user_prompt = (
        f"User query:\n{query}\n\n"
        f"Assistant answer:\n{answer}\n\n"
        "Classify sentiment strictly from the assistant answer."
    )
    try:
        raw, elapsed = llm.generate(SENTIMENT_SYSTEM_PROMPT, user_prompt, max_tokens=180)
        parsed = _parse_sentiment_json(raw)
        return parsed, elapsed
    except Exception:
        return _default_sentiment(), 0.0


def _parse_sentiment_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()

    try:
        data = json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            return _default_sentiment()
        try:
            data = json.loads(match.group(0))
        except Exception:
            return _default_sentiment()

    label = str(data.get("sentiment_label", "neutral")).strip().lower()
    if label not in {"positive", "negative", "neutral", "mixed"}:
        label = "neutral"

    score = _clamp_float(data.get("sentiment_score", 0.0), -1.0, 1.0)
    confidence = _clamp_float(data.get("confidence", 0.5), 0.0, 1.0)
    rationale = str(data.get("rationale", "Sentiment could not be confidently inferred.")).strip()
    if not rationale:
        rationale = "Sentiment could not be confidently inferred."

    return {
        "sentiment_label": label,
        "sentiment_score": round(score, 3),
        "confidence": round(confidence, 3),
        "rationale": rationale,
    }


def _clamp_float(value, lo: float, hi: float) -> float:
    try:
        num = float(value)
    except Exception:
        num = 0.0
    return max(lo, min(hi, num))


def _default_sentiment() -> dict:
    return {
        "sentiment_label": "neutral",
        "sentiment_score": 0.0,
        "confidence": 0.5,
        "rationale": "Sentiment could not be confidently inferred.",
    }
