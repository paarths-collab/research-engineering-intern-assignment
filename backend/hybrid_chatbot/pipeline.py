"""
hybrid_chatbot/pipeline.py
-------------------------
Dataset-grounded chatbot pipeline with optional DuckDuckGo web search.
"""

from __future__ import annotations

import logging
import math
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from .dataset_context import DatasetContextStore
from .llm_client import LLMClient
from .sql_engine import COVERAGE_NONE, COVERAGE_PARTIAL, Coverage, SQLPlan, SQLStore, SQLTranslator
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

ANSWER_MODES = (
    "deterministic_sql",
    "deterministic_dataset",
    "llm_synthesis",
    "fallback_template",
    "out_of_dataset",
    "sql_unavailable",
    "insufficient_coverage",
)

DATASET_NAME = "NarrativeSignal Reddit narrative dataset"
DATASET_DESCRIPTION = (
    "Historical snapshot of Reddit posts, narratives, domains and subreddit metrics "
    "(CSV-derived tables); it is not live data."
)

# SQL result states reported in `sql.status`.
SQL_OK = "ok"
SQL_NOT_APPLICABLE = "not_applicable"  # no keyword template matched the question
SQL_UNAVAILABLE = "unavailable"  # a required table is missing / no database could be built
SQL_INSUFFICIENT = "insufficient_coverage"  # table present but no data for the window/entity/values
SQL_ERROR = "error"


@dataclass
class SQLResult:
    plan: SQLPlan | None = None
    rows: list[dict] = field(default_factory=list)
    error: str | None = None
    status: str = SQL_NOT_APPLICABLE
    missing_tables: list[str] = field(default_factory=list)
    coverage: Coverage | None = None
    reason: str | None = None


class ChatPipeline:
    def __init__(
        self,
        llm: LLMClient,
        sql_store: SQLStore | None = None,
        dataset_store: DatasetContextStore | None = None,
        web: WebSearchClient | None = None,
    ):
        self.llm = llm
        self.dataset_store = dataset_store or DatasetContextStore()
        self.sql_store = sql_store or SQLStore()
        self.sql_translator: SQLTranslator | None = None
        self._sql_ready = False
        self.web = web or WebSearchClient()

    def run(self, query: str, web_search: bool = False, dataset_top_k: int = 8) -> dict:
        timings: dict[str, float] = {}
        t_start = time.perf_counter()

        def finish(answer, route, mode, llm_used, dataset_hits, sql_res, web_hits, evidence) -> dict:
            if sql_res.plan is not None and sql_res.plan.notes and sql_res.status == SQL_OK:
                answer = f"{answer} {' '.join(sql_res.plan.notes)}"
            timings["total"] = round(time.perf_counter() - t_start, 3)
            return {
                "answer": answer,
                "route": route,
                "answer_mode": mode,
                "llm_used": llm_used,
                "timing": timings,
                "dataset_chunks": dataset_hits,
                "sql": _sql_payload(sql_res),
                "web_articles": web_hits,
                "dataset": self._dataset_payload(evidence),
                "evidence": evidence,
                "retrieval": {
                    "method": "lexical_token_overlap",
                    "sql": "keyword_template",
                    "embeddings": False,
                    "dataset_top_k": dataset_top_k,
                    "web": "duckduckgo_html" if web_search else "disabled",
                },
            }

        def no_llm() -> None:
            timings["llm"] = 0.0
            timings["route"] = 0.0

        # Dataset grounding (always on)
        t0 = time.perf_counter()
        dataset_hits = self.dataset_store.search(query, top_k=dataset_top_k)
        timings["dataset"] = round(time.perf_counter() - t0, 3)

        # SQL grounding (best effort)
        t0 = time.perf_counter()
        sql_res = self._run_sql(query)
        timings["sql"] = round(time.perf_counter() - t0, 3)

        # A question whose SQL template needs data we do not have must say so, never
        # fall through to a ranking/analysis built from nothing.
        if sql_res.status == SQL_UNAVAILABLE:
            no_llm()
            return finish(
                _sql_unavailable_message(sql_res),
                "chat_sql_unavailable",
                "sql_unavailable",
                False,
                dataset_hits,
                sql_res,
                [],
                [],
            )

        # Missing data is not zero: a window/entity/value with no coverage gets an
        # explicit state, never "0 mentions" or an empty ranking presented as an answer.
        if sql_res.status == SQL_INSUFFICIENT:
            no_llm()
            return finish(
                _insufficient_coverage_message(sql_res),
                "chat_insufficient_coverage",
                "insufficient_coverage",
                False,
                dataset_hits,
                sql_res,
                [],
                [],
            )

        # Deterministic guardrail for known ranking queries so LLM wording cannot
        # incorrectly claim the data is missing when snippets are present.
        sql_direct = _maybe_direct_sql_answer(query, sql_res.rows)
        if sql_direct:
            no_llm()
            return finish(
                sql_direct, "chat_sql_direct", "deterministic_sql", False,
                dataset_hits, sql_res, [], _sql_evidence(sql_res),
            )
        dataset_direct = _maybe_direct_dataset_answer(query, dataset_hits)
        if dataset_direct:
            answer, hit = dataset_direct
            no_llm()
            return finish(
                answer, "chat_sql_direct", "deterministic_dataset", False,
                dataset_hits, sql_res, [], [_snippet_evidence(hit)],
            )

        dataset_relevant = _is_dataset_relevant(query, dataset_hits, sql_res.plan, sql_res.rows)
        if not dataset_relevant and not web_search:
            no_llm()
            return finish(
                _not_in_dataset_message(query), "chat_out_of_dataset", "out_of_dataset", False,
                dataset_hits, sql_res, [], [],
            )

        # Optional web search + scrape
        web_hits: list[dict] = []
        if web_search:
            t0 = time.perf_counter()
            # Clean query for DDG
            clean_query = re.sub(r"\(use web search\)", "", query, flags=re.IGNORECASE).strip()
            web_hits = self.web.search_and_scrape(clean_query, max_results=4)
            timings["web_search"] = round(time.perf_counter() - t0, 3)
            if not dataset_relevant and not web_hits:
                no_llm()
                return finish(
                    (
                        f"This question does not appear in the current NarrativeSignal datasets, and no web results "
                        f"were retrieved for '{query}'. Try rephrasing or enabling a broader web query."
                    ),
                    "chat_web_no_results",
                    "out_of_dataset",
                    False,
                    dataset_hits,
                    sql_res,
                    web_hits,
                    [],
                )

        # Only claim the web route when web results were actually used.
        route = "chat_web" if web_hits else "chat_dataset"
        # The dataset snippets only count as evidence when the question is about the dataset.
        used_hits = dataset_hits[:10] if dataset_relevant else []

        # LLM synthesis
        t0 = time.perf_counter()
        mode = "llm_synthesis"
        try:
            user_prompt = _build_chat_prompt(
                query=query,
                dataset_summary=self._dataset_summary(),
                dataset_hits=used_hits,
                sql_plan=sql_res.plan,
                sql_rows=sql_res.rows,
                sql_error=sql_res.error,
                sql_coverage=sql_res.coverage,
                web_hits=web_hits,
                web_search=web_search,
            )
            max_tokens = 900 if web_search else 500
            answer, llm_time = self.llm.generate(CHAT_SYSTEM_PROMPT, user_prompt, max_tokens=max_tokens)
            answer = _force_single_paragraph(answer)
            if not answer:
                raise RuntimeError("LLM returned an empty answer")
        except Exception as exc:
            logger.warning("LLM unavailable: %s", exc)
            mode = "fallback_template"
            used_hits = used_hits[:2]
            web_hits_used = web_hits[:2]
            answer = _fallback_answer(
                query=query,
                dataset_hits=used_hits,
                sql_plan=sql_res.plan,
                sql_rows=sql_res.rows,
                sql_error=sql_res.error,
                sql_coverage=sql_res.coverage,
                web_hits=web_hits,
                web_search=web_search,
            )
            llm_time = 0.0
        else:
            web_hits_used = web_hits[:5]
        timings["llm"] = round(llm_time, 3)
        timings["route"] = round(time.perf_counter() - t0 - llm_time, 3)

        evidence = (
            _sql_evidence(sql_res)
            + [_snippet_evidence(h) for h in used_hits]
            + [_web_evidence(h) for h in web_hits_used if h.get("url")]
        )
        logger.info("Route=%s mode=%s dataset_hits=%s web_hits=%s", route, mode, len(dataset_hits), len(web_hits))

        return finish(
            answer, route, mode, mode == "llm_synthesis",
            dataset_hits, sql_res, web_hits, evidence,
        )

    def _dataset_summary(self) -> str:
        summary = self.dataset_store.summary()
        start, end = self.sql_store.dataset_date_range()
        if start and end:
            summary += f" The data is a historical snapshot covering {start.isoformat()} to {end.isoformat()}."
        return summary

    def _dataset_payload(self, evidence: list[dict]) -> dict:
        try:
            start, end = self.sql_store.dataset_date_range()
        except Exception as exc:  # noqa: BLE001 - provenance must never break an answer
            logger.warning("Dataset date range unavailable: %s", exc)
            start = end = None
        tables_used: list[str] = []
        for item in evidence:
            names = item.get("tables") or ([item["table"]] if item.get("table") else [])
            for name in names:
                if name not in tables_used:
                    tables_used.append(name)
        return {
            "name": DATASET_NAME,
            "description": DATASET_DESCRIPTION,
            "date_range": {
                "start": start.isoformat() if start else None,
                "end": end.isoformat() if end else None,
            },
            "snapshot": "historical",
            "tables_used": tables_used,
        }

    def _ensure_sql_ready(self) -> None:
        if self._sql_ready and self.sql_translator is not None:
            return
        self.sql_store.initialize()  # never raises; outcome is in sql_store.status
        self.sql_translator = SQLTranslator(valid_subreddits=self.sql_store.valid_subreddits())
        self._sql_ready = True

    def _run_sql(self, query: str) -> SQLResult:
        try:
            self._ensure_sql_ready()
        except Exception as exc:
            logger.warning("SQL init unavailable: %s", exc)
            return SQLResult(error=f"SQL init failed: {exc}", status=SQL_UNAVAILABLE)

        if self.sql_translator is None:
            return SQLResult(error="SQL translator unavailable.", status=SQL_UNAVAILABLE)

        plan = self.sql_translator.build_plan(query, reference_date=self.sql_store.dataset_max_date())
        if plan is None:
            return SQLResult()

        if plan.unsupported_reason:
            window = {"start": plan.date_range[0], "end": plan.date_range[1]} if plan.date_range else None
            return SQLResult(
                plan=plan, status=SQL_INSUFFICIENT, reason=plan.unsupported_reason,
                coverage=Coverage(COVERAGE_NONE, plan.unsupported_reason, window),
            )

        missing = self.sql_store.missing_for(plan.tables)
        if missing:
            state = self.sql_store.status
            detail = f" ({state.error})" if state.error else ""
            return SQLResult(
                plan=plan,
                error=f"SQL data unavailable: required table(s) not available: {', '.join(missing)}{detail}",
                status=SQL_UNAVAILABLE,
                missing_tables=missing,
            )

        try:
            coverage = self.sql_store.check_coverage(plan)
            if coverage.status == COVERAGE_NONE:
                return SQLResult(
                    plan=plan, status=SQL_INSUFFICIENT, coverage=coverage, reason=coverage.reason,
                )
            df = self.sql_store.execute(plan.sql, plan.params)
            self._note_boundary_tie(plan, df)
            raw_rows = [_clean_row(r) for r in df.to_dict(orient="records")]
        except Exception as exc:
            logger.warning("SQL execution failed: %s", exc)
            return SQLResult(plan=plan, error=f"SQL query failed: {exc}", status=SQL_ERROR)

        # NULL / NaN / inf values are missing data, never a number to rank or report.
        rows = [r for r in raw_rows if all(r.get(m) is not None for m in plan.metrics)]
        if not rows:
            reason = (
                "The query matched rows, but every value in them is missing (NULL or non-finite)."
                if raw_rows
                else "The query matched no rows for the requested scope, so there is nothing to rank or count."
            )
            return SQLResult(plan=plan, status=SQL_INSUFFICIENT, coverage=coverage, reason=reason)
        return SQLResult(plan=plan, rows=rows, status=SQL_OK, coverage=coverage)


    def _note_boundary_tie(self, plan: SQLPlan, df) -> None:
        """Add a note when the LIMIT cut-off falls inside a tie on the ranked value.

        The secondary ORDER BY keys make the shown rows deterministic, but the user should
        know that equally ranked items beyond the cut-off are not listed.
        """
        if not plan.limit or not plan.rank_by or len(df) < plan.limit:
            return
        probe_sql = re.sub(r"LIMIT\s+\d+\s*$", f"LIMIT {plan.limit + 1}", plan.sql)
        if probe_sql == plan.sql:
            return
        try:
            probe = self.sql_store.execute(probe_sql, plan.params)
            if len(probe) <= plan.limit:
                return
            last = _clean_value(probe[plan.rank_by].iloc[plan.limit - 1])
            following = _clean_value(probe[plan.rank_by].iloc[plan.limit])
        except Exception as exc:  # noqa: BLE001 - the note is best effort, never fatal
            logger.warning("Tie check skipped: %s", exc)
            return
        if last is None or last != following:
            return
        tie_break = f"; ties are ordered by {plan.tie_break} (ascending)" if plan.tie_break else ""
        plan.notes.append(
            f"Tie at the result boundary: ranks {plan.limit} and {plan.limit + 1} share the same "
            f"{plan.rank_by} ({last}), so equally ranked items beyond the cut-off are not shown{tie_break}."
        )


def _build_chat_prompt(
    query: str,
    dataset_summary: str,
    dataset_hits: list[dict],
    sql_plan: SQLPlan | None,
    sql_rows: list[dict],
    sql_error: str | None,
    sql_coverage: Coverage | None,
    web_hits: list[dict],
    web_search: bool,
) -> str:
    dataset_context = _format_dataset_hits(dataset_hits)
    sql_context = _format_sql_evidence(sql_plan, sql_rows, sql_error, sql_coverage)
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
        meta = f" row={h['row_key']}" if h.get("row_key") else ""
        if h.get("date"):
            meta += f" date={h['date']}"
        lines.append(f"[dataset:{i}] source={src}{meta} score={score}: {text}")
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


def _format_sql_evidence(
    sql_plan: SQLPlan | None,
    sql_rows: list[dict],
    sql_error: str | None,
    sql_coverage: Coverage | None = None,
) -> str:
    if sql_plan is None:
        if sql_error:
            return f"SQL unavailable: {sql_error}"
        return "No SQL plan matched this query."
    header = f"Plan: {sql_plan.description}. Query: {sql_plan.sql}"
    if sql_error:
        return f"{header}\nStatus: {sql_error}"
    if not sql_rows:
        return f"{header}\nStatus: Query ran but returned no rows. This is not a count of zero."

    lines = [header]
    if sql_plan.params:
        lines.append(f"Parameters: {sql_plan.params}")
    if sql_coverage is not None and sql_coverage.status == COVERAGE_PARTIAL:
        lines.append(f"Coverage warning: {sql_coverage.reason}")
    for note in sql_plan.notes:
        lines.append(f"Note: {note}")
    prompt_rows = sql_rows if sql_plan.kind == "series" else sql_rows[:10]
    for i, row in enumerate(prompt_rows, start=1):
        row_text = ", ".join(f"{k}={row[k]}" for k in row.keys())
        lines.append(f"[sql:{i}] {row_text}")
    return "\n".join(lines)


def _fallback_answer(
    query: str,
    dataset_hits: list[dict],
    sql_plan: SQLPlan | None,
    sql_rows: list[dict],
    sql_error: str | None,
    sql_coverage: Coverage | None,
    web_hits: list[dict],
    web_search: bool,
) -> str:
    direct_sql = _maybe_direct_sql_answer(query, sql_rows)
    if direct_sql:
        return _force_single_paragraph(direct_sql)
    coverage_note = (
        f" Note: {sql_coverage.reason}" if sql_coverage is not None and sql_coverage.status == COVERAGE_PARTIAL else ""
    )

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
        base += f"SQL results indicate: {top_sql}.{coverage_note} "
        if sql_plan.kind == "series":
            peak = max(sql_rows, key=lambda row: row.get("post_count", 0))
            base += (
                f"The complete series contains {len(sql_rows)} observations from {sql_rows[0]['date']} "
                f"through {sql_rows[-1]['date']}; its peak is {peak.get('post_count')} posts on {peak['date']}. "
            )
    elif sql_error:
        base += f"SQL execution was unavailable ({sql_error}). "
    elif sql_plan and not sql_rows:
        base += "A matching SQL query ran but returned no rows (this is not a count of zero). "
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


def _sql_payload(res: SQLResult) -> dict:
    plan = res.plan
    return {
        "description": plan.description if plan else None,
        "query": plan.sql if plan else None,
        "rows": res.rows,
        "error": res.error,
        "status": res.status,
        "reason": res.reason,
        "coverage": res.coverage.to_dict() if res.coverage else None,
        "params": list(plan.params) if plan else [],
        "tables": plan.tables if plan else [],
        "missing_tables": res.missing_tables,
        "notes": list(plan.notes) if plan else [],
        "date_window": (
            {"start": plan.date_range[0], "end": plan.date_range[1]} if plan and plan.date_range else None
        ),
    }


def _sql_unavailable_message(res: SQLResult) -> str:
    tables = ", ".join(res.missing_tables) or "the SQL database"
    desc = res.plan.description.lower() if res.plan else "this question"
    return (
        f"The data needed to answer this ({desc}) is currently unavailable: "
        f"the NarrativeSignal table(s) {tables} could not be loaded, so no result can be given. "
        "No figures were estimated."
    )


def _insufficient_coverage_message(res: SQLResult) -> str:
    desc = res.plan.description.lower() if res.plan else "this question"
    return (
        f"The NarrativeSignal dataset does not have enough coverage to answer this ({desc}). "
        f"{res.reason or 'No data is available for the requested scope.'} "
        "Missing data is not the same as zero, so no count or ranking is reported."
    )


def _clean_value(value):
    """JSON-safe, reproducible scalar: dates as ISO strings (YYYY-MM-DD for dates and
    midnight timestamps), NaN/NaT/inf as None, numpy/Decimal scalars as plain Python numbers."""
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        if value != value:  # NaT != NaT
            return None
        if (
            isinstance(value, datetime)
            and value.tzinfo is None
            and (value.hour, value.minute, value.second, value.microsecond, getattr(value, "nanosecond", 0)) == (0,) * 5
        ):
            return value.date().isoformat()  # a DATE column read back as a midnight timestamp
        return value.isoformat()
    if isinstance(value, Decimal):
        value = float(value)
    elif hasattr(value, "item") and callable(value.item):  # numpy scalar
        try:
            value = value.item()
        except (TypeError, ValueError):
            pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        if value != value:
            return None
    except (TypeError, ValueError):
        pass
    return value


def _clean_row(row: dict) -> dict:
    return {k: _clean_value(v) for k, v in row.items()}


def _sql_evidence(res: SQLResult) -> list[dict]:
    if res.plan is None or res.status != SQL_OK:
        return []
    return [
        {
            "type": "sql",
            "tables": list(res.plan.tables),
            "description": res.plan.description,
            "query": res.plan.sql,
            "rows": res.rows,
            "row_count": len(res.rows),
        }
    ]


def _snippet_evidence(hit: dict) -> dict:
    return {
        "type": "dataset_snippet",
        "table": hit.get("table") or hit.get("source"),
        "row_key": hit.get("row_key"),
        "row_index": hit.get("row_index"),
        "date": hit.get("date"),
        "text": hit.get("text"),
        "score": hit.get("score"),
    }


def _web_evidence(hit: dict) -> dict:
    return {
        "type": "web",
        "url": hit.get("url"),
        "title": hit.get("title"),
        "source": hit.get("source"),
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


def _maybe_direct_dataset_answer(query: str, dataset_hits: list[dict]) -> tuple[str, dict] | None:
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
    best_hit: dict | None = None

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
            best_hit = hit

    if best_subreddit is None or best_hit is None:
        return None
    return (
        f"The subreddit with the highest echo-chamber lift is {best_subreddit} "
        f"({best_lift:.6f}).",
        best_hit,
    )
