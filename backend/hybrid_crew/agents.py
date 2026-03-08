"""
hybrid_crew/agents.py
---------------------
Full Research-Style (Option B) CrewAI architecture.

Agents:
  1. PlannerAgent   — decomposes a complex query into typed sub-tasks (LLM only, max 1 iter)
  2. RouterAgent    — picks execution mode based on planner output   (LLM only, max 1 iter)
  3. SQLAgent       — structured data retrieval via execute_sql / analyze_bridges (max 3 iter)
  4. VectorAgent    — semantic post retrieval via search_vectors     (max 2 iter)
  5. ForensicAgent  — synthesis of evidence into ForensicReport      (LLM only, max 1 iter)
  6. ReviewerAgent  — grounds the forensic answer against evidence    (LLM only, max 1 iter)

All agents produce Pydantic output. No recursive loops.
Guardrails are enforced at the tool layer (tools_sql, tools_vector).
"""

import json
import re
import logging
from typing import Literal, List, Optional

from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import SystemMessage, HumanMessage

from hybrid.tools_sql import execute_sql, analyze_bridges
from hybrid.tools_vector import search_vectors
from hybrid.constants import VALID_SUBS_STR, DATE_START, DATE_END, trim_schema

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic output models
# ═══════════════════════════════════════════════════════════════════════════════

class PlannerSubTask(BaseModel):
    type: Literal["sql", "vector", "hybrid"]
    description: str = Field(..., description="Short description of what this sub-task retrieves.")


class PlannerOutput(BaseModel):
    sub_tasks: List[PlannerSubTask] = Field(
        ..., description="Ordered list of sub-tasks needed to answer the query."
    )
    overall_strategy: str = Field(
        ..., description="One sentence describing the overall retrieval strategy."
    )


class RouteDecision(BaseModel):
    route: Literal["sql_only", "vector_only", "hybrid"]
    reason: str


class EvidencePayload(BaseModel):
    evidence: str = Field(
        ..., description="Raw tool output only. No analysis, no summary, no invented values."
    )


class ForensicReport(BaseModel):
    answer: str = Field(
        ..., description="3-4 sentence answer using ONLY values present in the evidence."
    )
    follow_up: List[str] = Field(
        default_factory=list,
        description="Optional follow-up questions the user might find useful (max 2)."
    )


class ReviewReport(BaseModel):
    answer: str = Field(
        ..., description="Final polished answer, corrected for any grounding issues."
    )
    issues: List[str] = Field(
        default_factory=list,
        description="List of grounding issues found. Empty means answer is clean."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _tool_calling_prompt(system_text: str) -> ChatPromptTemplate:
    """Creates a ChatPromptTemplate suitable for create_tool_calling_agent."""
    return ChatPromptTemplate.from_messages([
        SystemMessage(content=system_text),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])


def _parse_evidence(raw: str, label: str) -> EvidencePayload:
    """Extracts EvidencePayload from agent output string."""
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
    try:
        data = json.loads(cleaned)
        return EvidencePayload(evidence=data.get("evidence", cleaned))
    except Exception:
        logger.debug(f"[{label}Agent] Non-JSON output, wrapping.")
        return EvidencePayload(evidence=cleaned if cleaned else "No evidence retrieved.")


def _safe_structured_invoke(structured_llm, messages: list, fallback):
    """Invoke a structured LLM with up to 2 attempts. Returns fallback on failure."""
    for attempt in range(1, 3):
        try:
            return structured_llm.invoke(messages)
        except Exception as exc:
            logger.warning(f"Structured invoke attempt {attempt} failed: {exc}")
            if attempt == 1:
                messages.append(HumanMessage(content=(
                    "Retry. Return ONLY valid JSON matching the required schema. "
                    "Do not add explanations."
                )))
    return fallback


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Planner Agent
# ═══════════════════════════════════════════════════════════════════════════════

_PLANNER_SYSTEM = """You are a query planning specialist for a political Reddit analysis system.

YOUR ONLY JOB: Decompose the user query into concrete sub-tasks.

Sub-task types:
  - "sql"    : retrieve structured metrics (counts, rankings, scores, dates, specific authors).
  - "vector" : retrieve semantic post matches (themes, narratives, rhetoric — no numeric requirement).
  - "hybrid" : requires BOTH types in one sub-task.

Rules:
- Maximum 3 sub-tasks total.
- Be specific. Each sub-task must describe exactly what to retrieve.
- Do NOT answer the query. Only plan retrieval.
- Do NOT fabricate data.

Return a PlannerOutput JSON with 'sub_tasks' and 'overall_strategy'."""


class PlannerAgent:
    """Decomposes a complex query into typed retrieval sub-tasks. 1 LLM call, no tools."""

    def __init__(self, llm: ChatGroq):
        self._structured_llm = llm.with_structured_output(PlannerOutput)

    def plan(self, query: str) -> PlannerOutput:
        messages = [
            SystemMessage(content=_PLANNER_SYSTEM),
            HumanMessage(content=f'Plan retrieval for this query: "{query}"'),
        ]
        fallback = PlannerOutput(
            sub_tasks=[PlannerSubTask(type="hybrid", description=query)],
            overall_strategy="Fallback: run hybrid retrieval on the full query."
        )
        result = _safe_structured_invoke(self._structured_llm, messages, fallback)
        logger.info(f"[PlannerAgent] strategy={result.overall_strategy} | tasks={len(result.sub_tasks)}")
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Router Agent
# ═══════════════════════════════════════════════════════════════════════════════

_ROUTER_SYSTEM = """You are a routing controller for a political Reddit analysis system.

Given the user query AND the planner's sub-tasks, decide the execution mode.

ROUTING RULES:
- sql_only    : ALL sub-tasks are "sql" type. OR query is purely numeric/aggregate.
- vector_only : ALL sub-tasks are "vector" type. OR query asks for themes/narratives only.
- hybrid      : ANY sub-task is "hybrid", OR there is a mix of "sql" and "vector" tasks.

Deterministic overrides (highest priority):
- Contains a cluster_id like 'cluster 999' or numeric ID → sql_only
- Contains words: 'count', 'total', 'average', 'score', 'rank', 'highest', 'lowest' → sql_only
- Contains words: 'themes', 'narratives', 'rhetoric', 'sentiment', 'ideology' with NO numeric ask → vector_only
- Both types above → hybrid

Return route and one-sentence reason."""


class RouterAgent:
    """Picks the execution mode. 1 LLM call, no tools, structured output."""

    def __init__(self, llm: ChatGroq):
        self._structured_llm = llm.with_structured_output(RouteDecision)

    def decide(self, query: str, plan: PlannerOutput) -> RouteDecision:
        plan_summary = "\n".join([
            f"  - [{t.type.upper()}] {t.description}" for t in plan.sub_tasks
        ])
        messages = [
            SystemMessage(content=_ROUTER_SYSTEM),
            HumanMessage(content=(
                f'User query: "{query}"\n\n'
                f'Planner sub-tasks:\n{plan_summary}\n\n'
                f'Overall strategy: {plan.overall_strategy}\n\n'
                f'Decide the execution route.'
            )),
        ]
        fallback = RouteDecision(route="hybrid", reason="Fallback: defaulting to hybrid.")
        result = _safe_structured_invoke(self._structured_llm, messages, fallback)
        logger.info(f"[RouterAgent] route={result.route} | {result.reason}")
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# 3. SQL Agent
# ═══════════════════════════════════════════════════════════════════════════════

_SQL_SYSTEM = """You are a structured data retrieval specialist for a Reddit political dataset.

YOUR ROLE: Retrieve raw SQL evidence only. Do NOT summarize, analyze, or answer.

RULES:
- NEVER fabricate numbers, author names, or subreddit names.
- NEVER use narrative_id, cluster_id as names. Use representative_title or topic_label.
- Valid subreddits: {subs}
- Date range: {start} to {end}. Filter: CAST(created_datetime AS DATE)
- CRITICAL: For final_influence_score, ALWAYS use author_influence table, not user_intelligence.
- CRITICAL: bridge_authors has ONLY columns: author, subreddit, post_count.
- CRITICAL: NEVER query bridge_authors directly. Use the analyze_bridges tool.
- Max 2 tool calls. Use the most direct query first. Stop when you have the data.
- If 0 results, return exactly: {{"evidence": "No rows returned."}}

RELEVANT SCHEMA:
{{schema}}

Return ONLY this JSON: {{"evidence": "<paste raw tool output here, unmodified>"}}"""


class SQLAgent:
    def __init__(self, llm: ChatGroq):
        self._llm = llm

    def run(self, query: str) -> EvidencePayload:
        schema = trim_schema(query)
        system = _SQL_SYSTEM.format(
            subs=VALID_SUBS_STR, start=DATE_START, end=DATE_END
        ).replace("{schema}", schema)

        tools = [execute_sql, analyze_bridges]
        prompt = _tool_calling_prompt(system)

        try:
            agent = create_tool_calling_agent(llm=self._llm, tools=tools, prompt=prompt)
            executor = AgentExecutor(
                agent=agent, tools=tools, max_iterations=3,
                handle_parsing_errors=True, verbose=True,
            )
            result = executor.invoke({"input": query})
            return _parse_evidence(result.get("output", ""), "SQL")
        except Exception as exc:
            logger.error(f"[SQLAgent] Error: {exc}")
            return EvidencePayload(evidence=f"SQL agent error: {str(exc)[:300]}")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Vector Agent
# ═══════════════════════════════════════════════════════════════════════════════

_VECTOR_SYSTEM = """You are a semantic retrieval specialist for a Reddit political dataset.

YOUR ROLE: Retrieve semantic matches only. Do NOT compute counts or produce analysis.

RULES:
- Use search_vectors with a short, relevant topic keyword (3-5 words max).
- Do NOT estimate trends or numeric patterns.
- Do NOT fabricate content.
- Return ONLY the raw tool output, unmodified.
- Max 2 tool calls total. Stop after first successful result.
- If no results: {"evidence": "No semantic matches found."}

Return ONLY this JSON: {"evidence": "<paste raw search results here, unmodified>"}"""


class VectorAgent:
    def __init__(self, llm: ChatGroq):
        self._llm = llm

    def run(self, query: str) -> EvidencePayload:
        tools = [search_vectors]
        prompt = _tool_calling_prompt(_VECTOR_SYSTEM)

        try:
            agent = create_tool_calling_agent(llm=self._llm, tools=tools, prompt=prompt)
            executor = AgentExecutor(
                agent=agent, tools=tools, max_iterations=2,
                handle_parsing_errors=True, verbose=True,
            )
            result = executor.invoke({"input": query})
            return _parse_evidence(result.get("output", ""), "Vector")
        except Exception as exc:
            logger.error(f"[VectorAgent] Error: {exc}")
            return EvidencePayload(evidence=f"Vector agent error: {str(exc)[:300]}")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Forensic Agent
# ═══════════════════════════════════════════════════════════════════════════════

_FORENSIC_SYSTEM = """You are a forensic intelligence analyst. You have NO tools.

You receive:
  - The user question
  - SQL evidence (structured database results)
  - Vector evidence (semantic post matches)

STRICT RULES:
1. Use ONLY values that appear verbatim in the provided evidence.
2. If evidence is empty or "No rows returned", state data is not available.
3. Do NOT invent numbers, percentages, author names, or subreddit names.
4. Do NOT use narrative_id, cluster_id as names. Use representative_title or topic_label.
5. Do NOT reference dates not present in evidence.
6. Answer must be exactly 3-4 sentences.
7. Every subreddit you name must be one of: {subs}
8. Include up to 2 useful follow-up questions the user might ask."""


class ForensicAgent:
    def __init__(self, llm: ChatGroq):
        self._structured_llm = llm.with_structured_output(ForensicReport)

    def run(
        self,
        query: str,
        sql_evidence: Optional[EvidencePayload],
        vector_evidence: Optional[EvidencePayload],
    ) -> ForensicReport:
        from hybrid.constants import VALID_SUBS_STR as subs
        sql_text    = sql_evidence.evidence    if sql_evidence    else "Not retrieved."
        vector_text = vector_evidence.evidence if vector_evidence else "Not retrieved."

        system = _FORENSIC_SYSTEM.format(subs=subs)
        user_content = (
            f"QUESTION: {query}\n\n"
            f"SQL EVIDENCE (preserve header and layout exactly):\n{sql_text}\n\n"
            f"VECTOR EVIDENCE:\n{vector_text}\n\n"
            "Reference metrics exactly as shown. Do not rename columns. "
            "Produce the forensic report now."
        )
        messages = [SystemMessage(content=system), HumanMessage(content=user_content)]
        fallback = ForensicReport(answer="Data not available in current dataset.")
        result = _safe_structured_invoke(self._structured_llm, messages, fallback)
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Reviewer Agent
# ═══════════════════════════════════════════════════════════════════════════════

_REVIEWER_SYSTEM = """You are a quality reviewer for a forensic analyst's answer.

You receive:
  - The original user question
  - SQL evidence
  - Vector evidence
  - The analyst's answer (ForensicReport)

YOUR JOB: Verify the answer is grounded in the evidence.

CHECK FOR:
1. Numbers in the answer: do they appear in evidence? If not → flag.
2. Author names in the answer: do they appear in evidence? If not → flag.
3. Subreddits: are they in the valid list? {subs}
4. Hallucinated data not in evidence → flag.
5. Internal key leaks (narrative_id, cluster_id) used as names → flag.

If any issues: rewrite the relevant sentence(s) using only evidence values.
If answer is clean: return it unchanged with issues=[].

Return a ReviewReport JSON."""


class ReviewerAgent:
    def __init__(self, llm: ChatGroq):
        self._structured_llm = llm.with_structured_output(ReviewReport)

    def review(
        self,
        query: str,
        report: ForensicReport,
        sql_evidence: Optional[EvidencePayload],
        vector_evidence: Optional[EvidencePayload],
    ) -> ReviewReport:
        from hybrid.constants import VALID_SUBS_STR as subs
        sql_text    = sql_evidence.evidence    if sql_evidence    else "Not retrieved."
        vector_text = vector_evidence.evidence if vector_evidence else "Not retrieved."

        system = _REVIEWER_SYSTEM.format(subs=subs)
        user_content = (
            f"QUESTION: {query}\n\n"
            f"SQL EVIDENCE:\n{sql_text}\n\n"
            f"VECTOR EVIDENCE:\n{vector_text}\n\n"
            f"ANALYST ANSWER:\n{report.answer}\n\n"
            "Review the answer. Return a ReviewReport."
        )
        messages = [SystemMessage(content=system), HumanMessage(content=user_content)]
        fallback = ReviewReport(answer=report.answer, issues=["Reviewer failed; returning original answer."])
        result = _safe_structured_invoke(self._structured_llm, messages, fallback)
        if result.issues:
            logger.warning(f"[ReviewerAgent] Issues found: {result.issues}")
        else:
            logger.info("[ReviewerAgent] Answer approved — no issues.")
        return result
