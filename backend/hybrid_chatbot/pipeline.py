"""
hybrid_chatbot/pipeline.py
-------------------------
Dataset-grounded chatbot pipeline with optional DuckDuckGo web search.
"""

from __future__ import annotations

import logging
import re
import time

from .dataset_context import DatasetContextStore
from .llm_client import LLMClient
from .sql_engine import SQLPlan, SQLStore, SQLTranslator
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
    "If web evidence is provided, integrate it naturally."
)

class ChatPipeline:
    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.dataset_store = DatasetContextStore()
        self.sql_store = SQLStore()
        self.sql_translator: SQLTranslator | None = None
        self._sql_ready = False
        self.web = WebSearchClient()

    def run(self, query: str, web_search: bool = False, dataset_top_k: int = 8) -> dict:
        timings: dict[str, float] = {}
        t_start = time.perf_counter()

        # Dataset grounding (always on)
        t0 = time.perf_counter()
        dataset_hits = self.dataset_store.search(query, top_k=dataset_top_k)
        timings["dataset"] = round(time.perf_counter() - t0, 3)

        # SQL grounding (best effort)
        t0 = time.perf_counter()
        sql_plan, sql_rows, sql_error = self._run_sql(query)
        timings["sql"] = round(time.perf_counter() - t0, 3)

        # Deterministic guardrail for known ranking queries so LLM wording cannot
        # incorrectly claim the data is missing when snippets are present.
        direct_answer = _maybe_direct_sql_answer(query, sql_rows) or _maybe_direct_dataset_answer(query, dataset_hits)
        if direct_answer:
            timings["llm"] = 0.0
            timings["route"] = 0.0
            timings["total"] = round(time.perf_counter() - t_start, 3)
            return {
                "answer": direct_answer,
                "route": "chat_sql_direct",
                "timing": timings,
                "dataset_chunks": dataset_hits,
                "sql": _sql_payload(sql_plan, sql_rows, sql_error),
                "web_articles": [],
            }

        dataset_relevant = _is_dataset_relevant(query, dataset_hits, sql_plan, sql_rows)
        if not dataset_relevant and not web_search:
            timings["llm"] = 0.0
            timings["route"] = 0.0
            timings["total"] = round(time.perf_counter() - t_start, 3)
            return {
                "answer": _not_in_dataset_message(query),
                "route": "chat_out_of_dataset",
                "timing": timings,
                "dataset_chunks": dataset_hits,
                "sql": _sql_payload(sql_plan, sql_rows, sql_error),
                "web_articles": [],
            }

        # Optional web search + scrape
        web_hits: list[dict] = []
        if web_search:
            t0 = time.perf_counter()
            # Clean query for DDG
            clean_query = re.sub(r"\(use web search\)", "", query, flags=re.IGNORECASE).strip()
            web_hits = self.web.search_and_scrape(clean_query, max_results=4)
            timings["web_search"] = round(time.perf_counter() - t0, 3)
            if not dataset_relevant and not web_hits:
                timings["llm"] = 0.0
                timings["route"] = 0.0
                timings["total"] = round(time.perf_counter() - t_start, 3)
                return {
                    "answer": (
                        f"This question does not appear in the current NarrativeSignal datasets, and no web results "
                        f"were retrieved for '{query}'. Try rephrasing or enabling a broader web query."
                    ),
                    "route": "chat_web_no_results",
                    "timing": timings,
                    "dataset_chunks": dataset_hits,
                    "sql": _sql_payload(sql_plan, sql_rows, sql_error),
                    "web_articles": web_hits,
                }

        # LLM synthesis
        t0 = time.perf_counter()
        try:
            user_prompt = _build_chat_prompt(
                query=query,
                dataset_summary=self.dataset_store.summary(),
                dataset_hits=dataset_hits,
                sql_plan=sql_plan,
                sql_rows=sql_rows,
                sql_error=sql_error,
                web_hits=web_hits,
                web_search=web_search,
            )
            max_tokens = 900 if web_search else 500
            answer, llm_time = self.llm.generate(CHAT_SYSTEM_PROMPT, user_prompt, max_tokens=max_tokens)
            answer = _force_single_paragraph(answer)
        except Exception as exc:
            logger.warning("LLM unavailable: %s", exc)
            answer = _fallback_answer(
                query=query,
                dataset_hits=dataset_hits,
                sql_plan=sql_plan,
                sql_rows=sql_rows,
                sql_error=sql_error,
                web_hits=web_hits,
                web_search=web_search,
            )
            llm_time = 0.0
        timings["llm"] = round(llm_time, 3)
        timings["route"] = round(time.perf_counter() - t0 - llm_time, 3)

        timings["total"] = round(time.perf_counter() - t_start, 3)

        route = "chat_web" if web_search else "chat_dataset"
        logger.info("Route=%s dataset_hits=%s web_hits=%s", route, len(dataset_hits), len(web_hits))

        return {
            "answer": answer,
            "route": route,
            "timing": timings,
            "dataset_chunks": dataset_hits,
            "sql": _sql_payload(sql_plan, sql_rows, sql_error),
            "web_articles": web_hits,
        }

    def _ensure_sql_ready(self) -> None:
        if self._sql_ready and self.sql_translator is not None:
            return
        self.sql_store.initialize()
        valid_subreddits = self.sql_store.valid_subreddits()
        self.sql_translator = SQLTranslator(valid_subreddits=valid_subreddits)
        self._sql_ready = True

    def _run_sql(self, query: str) -> tuple[SQLPlan | None, list[dict], str | None]:
        try:
            self._ensure_sql_ready()
        except Exception as exc:
            logger.warning("SQL init unavailable: %s", exc)
            return None, [], f"SQL init failed: {exc}"

        if self.sql_translator is None:
            return None, [], "SQL translator unavailable."

        plan = self.sql_translator.build_plan(query, reference_date=self.sql_store.dataset_max_date())
        if plan is None:
            return None, [], None

        try:
            df = self.sql_store.execute(plan.sql)
            rows = df.head(20).to_dict(orient="records")
            return plan, rows, None
        except Exception as exc:
            logger.warning("SQL execution failed: %s", exc)
            return plan, [], f"SQL query failed: {exc}"


def _build_chat_prompt(
    query: str,
    dataset_summary: str,
    dataset_hits: list[dict],
    sql_plan: SQLPlan | None,
    sql_rows: list[dict],
    sql_error: str | None,
    web_hits: list[dict],
    web_search: bool,
) -> str:
    dataset_context = _format_dataset_hits(dataset_hits)
    sql_context = _format_sql_evidence(sql_plan, sql_rows, sql_error)
    if web_search:
        web_context = _format_web_hits(web_hits)
        return (
            f"PROJECT CONTEXT:\n{PROJECT_CONTEXT}\n\n"
            f"DATASET SUMMARY:\n{dataset_summary}\n\n"
            f"USER QUESTION:\n{query}\n\n"
            f"DATASET EVIDENCE:\n{dataset_context}\n\n"
            f"SQL EVIDENCE:\n{sql_context}\n\n"
            f"WEB EVIDENCE:\n{web_context}\n\n"
            "INSTRUCTIONS:\n"
            "- Answer as NarrativeSignal assistant and stay project-specific.\n"
            "- Use dataset and SQL evidence as primary grounding and enrich with web evidence where relevant.\n"
            "- Output exactly one paragraph (no headings, no bullet points, no labels).\n"
            "- Do not write phrases like 'Dataset Evidence' or 'Web context'.\n"
            "- If evidence is weak, mention limitations briefly within the same paragraph.\n"
            "- Keep claims tied to provided evidence only.\n"
        )

    return (
        f"PROJECT CONTEXT:\n{PROJECT_CONTEXT}\n\n"
        f"DATASET SUMMARY:\n{dataset_summary}\n\n"
        f"USER QUESTION:\n{query}\n\n"
        f"DATASET EVIDENCE:\n{dataset_context}\n\n"
        f"SQL EVIDENCE:\n{sql_context}\n\n"
        "INSTRUCTIONS:\n"
        "- Answer as NarrativeSignal assistant and stay project-specific.\n"
        "- Use only dataset and SQL evidence above.\n"
        "- Output exactly one paragraph (no headings, no bullet points, no labels).\n"
        "- Do not mention web search, web context, or that web search is disabled.\n"
        "- If evidence is weak, mention limitations briefly within the same paragraph.\n"
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


def _format_sql_evidence(sql_plan: SQLPlan | None, sql_rows: list[dict], sql_error: str | None) -> str:
    if sql_plan is None:
        if sql_error:
            return f"SQL unavailable: {sql_error}"
        return "No SQL plan matched this query."
    header = f"Plan: {sql_plan.description}. Query: {sql_plan.sql}"
    if sql_error:
        return f"{header}\nStatus: {sql_error}"
    if not sql_rows:
        return f"{header}\nStatus: Query ran but returned no rows."

    lines = [header]
    for i, row in enumerate(sql_rows[:10], start=1):
        row_text = ", ".join(f"{k}={row[k]}" for k in row.keys())
        lines.append(f"[sql:{i}] {row_text}")
    return "\n".join(lines)


def _fallback_answer(
    query: str,
    dataset_hits: list[dict],
    sql_plan: SQLPlan | None,
    sql_rows: list[dict],
    sql_error: str | None,
    web_hits: list[dict],
    web_search: bool,
) -> str:
    direct_sql = _maybe_direct_sql_answer(query, sql_rows)
    if direct_sql:
        return _force_single_paragraph(direct_sql)

    base = (
        "I could not reach the language model, so here is a concise dataset-and-SQL grounded summary for your question "
        f"'{query}'. "
    )
    if dataset_hits:
        top = "; ".join(str(h.get("text", "")) for h in dataset_hits[:2])
        base += f"Top matching dataset signals indicate: {top}. "
    else:
        base += "I could not find strong matching dataset signals for this query. "

    if sql_plan and sql_rows:
        top_sql = "; ".join(_row_summary(r) for r in sql_rows[:2])
        base += f"SQL results indicate: {top_sql}. "
    elif sql_error:
        base += f"SQL execution was unavailable ({sql_error}). "
    elif sql_plan and not sql_rows:
        base += "A matching SQL query ran but returned no rows. "
    else:
        base += "No SQL query template matched this question. "

    if web_search:
        if web_hits:
            web_top = "; ".join(f"{w.get('title')} ({w.get('source')})" for w in web_hits[:2])
            base += f"Relevant web articles retrieved include {web_top}."
        else:
            base += "No relevant web articles were retrieved."
    return _force_single_paragraph(base)


def _force_single_paragraph(text: str) -> str:
    clean = str(text or "")
    clean = re.sub(r"(?im)^\s*(dataset evidence|web context|web evidence|analysis|answer)\s*:\s*", "", clean)
    clean = re.sub(r"(?m)^\s*[-*]\s*", "", clean)
    clean = re.sub(r"\s*\n+\s*", " ", clean).strip()
    return clean


def _sql_payload(sql_plan: SQLPlan | None, sql_rows: list[dict], sql_error: str | None) -> dict:
    return {
        "description": sql_plan.description if sql_plan else None,
        "query": sql_plan.sql if sql_plan else None,
        "rows": sql_rows,
        "error": sql_error,
    }


def _row_summary(row: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in row.items())


def _is_dataset_relevant(query: str, dataset_hits: list[dict], sql_plan: SQLPlan | None, sql_rows: list[dict]) -> bool:
    if sql_rows:
        return True
    if sql_plan is not None:
        return True
    if not _looks_like_dataset_question(query):
        return False
    if not dataset_hits:
        return False
    top_score = max(float(h.get("score", 0.0)) for h in dataset_hits)
    return top_score >= 0.2


def _not_in_dataset_message(query: str) -> str:
    return (
        f"This question does not appear to be answerable from the current NarrativeSignal datasets: '{query}'. "
        "Enable Web Search to answer this from online sources."
    )


def _looks_like_dataset_question(query: str) -> bool:
    q = query.lower()
    dataset_terms = [
        "dataset", "narrative", "subreddit", "domain", "echo", "lift",
        "volume", "post", "author", "influence", "spread",
        "reddit", "elon", "musk", "trump", "news", "headline", "spike", "surge"
    ]
    return any(term in q for term in dataset_terms) or len(q) < 20


def _maybe_direct_sql_answer(query: str, sql_rows: list[dict]) -> str | None:
    q = query.lower()
    is_echo_extreme = (
        ("echo chamber" in q or "echo-chamber" in q or "echo" in q)
        and "lift" in q
        and ("highest" in q or "top" in q or "most" in q)
    )
    if not is_echo_extreme or not sql_rows:
        return None

    row = sql_rows[0]
    subreddit = row.get("subreddit")
    lift = row.get("lift")
    if subreddit is None or lift is None:
        return None
    try:
        lift_val = float(lift)
    except Exception:
        return f"The subreddit with the highest echo-chamber lift is {subreddit} ({lift})."
    return f"The subreddit with the highest echo-chamber lift is {subreddit} ({lift_val:.6f})."


def _maybe_direct_dataset_answer(query: str, dataset_hits: list[dict]) -> str | None:
    q = query.lower()
    is_echo_extreme = (
        ("echo chamber" in q or "echo-chamber" in q or "echo" in q)
        and "lift" in q
        and ("highest" in q or "top" in q or "most" in q)
    )
    if not is_echo_extreme:
        return None

    best_subreddit = None
    best_lift = float("-inf")

    for hit in dataset_hits:
        if hit.get("source") != "echo_chamber_scores":
            continue
        text = str(hit.get("text", ""))
        m = re.search(
            r"Subreddit\s+(.+?)\s+has echo-chamber lift score\s+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)",
            text,
            flags=re.IGNORECASE,
        )
        if not m:
            continue
        subreddit = m.group(1).strip()
        lift = float(m.group(2))
        if lift > best_lift:
            best_subreddit = subreddit
            best_lift = lift

    if best_subreddit is None:
        return None
    return (
        f"The subreddit with the highest echo-chamber lift is {best_subreddit} "
        f"({best_lift:.6f})."
    )
