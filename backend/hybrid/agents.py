"""
hybrid/agents.py
-----------------
Three specialist agents — LangChain tool-calling (not ReAct).

Fix 1: create_tool_calling_agent replaces create_react_agent.
        Tool-calling agents are cheaper, faster, more deterministic.
        No chain-of-thought traces. No reasoning loops.

Fix 4: Vector embedding model is cached at import (database.py singleton),
        normalised at load time, dot-product at query time. No per-request reload.

Fix 5: Structured Pydantic output enforced on ALL agents:
        - SQL/Vector agents return EvidencePayload
        - Forensic agent returns ForensicReport

Agent role isolation (enforced at tool list level):
    SQL Agent     -> [execute_sql, analyze_bridges] only
    Vector Agent  -> [search_vectors] only
    Forensic Agent -> [] (no tools — physically cannot call anything)
"""

import json
import re
import logging
from typing import Optional

from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import SystemMessage

from hybrid.tools_sql import execute_sql, analyze_bridges
from hybrid.tools_vector import search_vectors
from hybrid.constants import VALID_SUBS_STR, DATE_START, DATE_END, trim_schema

logger = logging.getLogger(__name__)


# ── Pydantic output models ─────────────────────────────────────────────────────

class EvidencePayload(BaseModel):
    """Structured output for SQL and Vector agents."""
    evidence: str = Field(
        ...,
        description="Raw tool output only. No analysis, no summary, no invented values."
    )


class ForensicReport(BaseModel):
    """Structured output for Forensic agent."""
    answer: str = Field(
        ...,
        description="3-4 sentence answer using only values present in the evidence."
    )


# ── Shared prompt builder for tool-calling agents ─────────────────────────────
# create_tool_calling_agent requires a ChatPromptTemplate with
# a MessagesPlaceholder named "agent_scratchpad".

def _tool_calling_prompt(system_text: str) -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([
        SystemMessage(content=system_text),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])


# ── SQL Agent ──────────────────────────────────────────────────────────────────

_SQL_SYSTEM = """You are a structured data retrieval specialist for a Reddit political dataset.

YOUR ROLE: Retrieve raw SQL evidence only. Do NOT summarize, analyze, or answer the question.

RULES:
- NEVER fabricate numbers, author names, or subreddit names.
- NEVER use narrative_id, cluster_id, or internal_system_id as names.
  Use representative_title or topic_label for narrative names.
- Valid subreddits: {subs}
- Date range: {start} to {end}. Filter: CAST(created_datetime AS DATE)
- CRITICAL: When querying final_influence_score, ALWAYS use author_influence table, not user_intelligence.
- CRITICAL: The table bridge_authors has ONLY columns: author, subreddit, post_count.
- CRITICAL: You must NEVER query bridge_authors directly. Use the analyze_bridges tool instead.
- If you attempt to query bridge_authors directly, the request will be rejected.
- Max 2 tool calls. Use the most direct query first. Stop when you have the data.
- If 0 results, return exactly: {{"evidence": "No rows returned."}}

RELEVANT SCHEMA:
{{schema}}

Return ONLY this JSON structure:
{{"evidence": "<paste raw tool output here, unmodified>"}}"""


class SQLAgent:
    def __init__(self, llm: ChatGroq):
        self._structured_llm = llm.with_structured_output(EvidencePayload)
        self._llm = llm

    def run(self, query: str) -> EvidencePayload:
        schema = trim_schema(query)
        system = _SQL_SYSTEM.format(
            subs=VALID_SUBS_STR, start=DATE_START, end=DATE_END
        ).replace("{schema}", schema)

        tools = [execute_sql, analyze_bridges]
        prompt = _tool_calling_prompt(system)

        try:
            agent = create_tool_calling_agent(
                llm=self._llm,
                tools=tools,
                prompt=prompt,
            )
            executor = AgentExecutor(
                agent=agent,
                tools=tools,
                max_iterations=3,
                handle_parsing_errors=True,
                verbose=True,
            )
            result = executor.invoke({"input": query})
            raw = result.get("output", "")
            return _parse_evidence(raw, "SQL")
        except Exception as exc:
            logger.error(f"[SQLAgent] Error: {exc}")
            return EvidencePayload(evidence=f"SQL agent error: {str(exc)[:300]}")


# ── Vector Agent ───────────────────────────────────────────────────────────────

_VECTOR_SYSTEM = """You are a semantic retrieval specialist for a Reddit political dataset.

YOUR ROLE: Retrieve semantic matches only. Do NOT compute counts or produce analysis.

RULES:
- Use search_vectors with a short, relevant topic keyword (3-5 words max).
- Do NOT estimate trends or numeric patterns.
- Do NOT fabricate content.
- Return ONLY the raw tool output, unmodified.
- Max 2 tool calls total. Stop after first successful result.
- If no results: {"evidence": "No semantic matches found."}

Return ONLY this JSON structure:
{"evidence": "<paste raw search results here, unmodified>"}"""


class VectorAgent:
    def __init__(self, llm: ChatGroq):
        self._llm = llm

    def run(self, query: str) -> EvidencePayload:
        tools = [search_vectors]
        prompt = _tool_calling_prompt(_VECTOR_SYSTEM)

        try:
            agent = create_tool_calling_agent(
                llm=self._llm,
                tools=tools,
                prompt=prompt,
            )
            executor = AgentExecutor(
                agent=agent,
                tools=tools,
                max_iterations=2,
                handle_parsing_errors=True,
                verbose=True,
            )
            result = executor.invoke({"input": query})
            raw = result.get("output", "")
            return _parse_evidence(raw, "Vector")
        except Exception as exc:
            logger.error(f"[VectorAgent] Error: {exc}")
            return EvidencePayload(evidence=f"Vector agent error: {str(exc)[:300]}")


# ── Forensic Agent ─────────────────────────────────────────────────────────────

_FORENSIC_SYSTEM = """You are a forensic intelligence analyst. You have NO tools.

You will receive:
  - The user question
  - SQL evidence (structured database results)
  - Vector evidence (semantic post matches)

STRICT RULES:
1. Use ONLY values that appear verbatim in the provided evidence.
2. If evidence is empty or "No rows returned", state data is not available.
3. Do NOT invent numbers, percentages, author names, or subreddit names.
4. Do NOT use narrative_id, cluster_id, or duplicate_cluster_id as names.
   These are internal opaque keys. Only use representative_title or topic_label.
5. Do NOT reference dates not present in evidence.
6. Do NOT compute or estimate percentages unless they appear in evidence.
7. Answer must be exactly 3-4 sentences.
8. Every subreddit you name must be one of: {subs}"""


class ForensicAgent:
    def __init__(self, llm: ChatGroq):
        # Bind structured output directly — no tools, no agent loop
        self._structured_llm = llm.with_structured_output(ForensicReport)

    def run(
        self,
        query: str,
        sql_evidence: Optional[EvidencePayload],
        vector_evidence: Optional[EvidencePayload],
    ) -> ForensicReport:
        """
        Pure synthesis call. No tools. Max 1 retry on parse failure.
        Uses llm.with_structured_output for schema-enforced JSON.
        """
        sql_text    = sql_evidence.evidence    if sql_evidence    else "Not retrieved."
        vector_text = vector_evidence.evidence if vector_evidence else "Not retrieved."

        from langchain.schema import HumanMessage, SystemMessage
        system = _FORENSIC_SYSTEM.format(subs=VALID_SUBS_STR)
        user_content = (
            f"QUESTION: {query}\n\n"
            f"SQL EVIDENCE (preserve header and table layout exactly):\n{sql_text}\n\n"
            f"VECTOR EVIDENCE:\n{vector_text}\n\n"
            "You must reference metrics exactly as shown in the evidence.\n"
            "Do not rename columns.\n"
            "Do not infer metrics.\n"
            "Produce the forensic report now."
        )

        messages = [
            SystemMessage(content=system),
            HumanMessage(content=user_content),
        ]

        for attempt in range(1, 3):
            try:
                report: ForensicReport = self._structured_llm.invoke(messages)

                return ForensicReport(answer=report.answer)

            except Exception as exc:
                logger.warning(f"[ForensicAgent] Attempt {attempt} failed: {exc}")
                if attempt == 1:
                    from langchain.schema import HumanMessage
                    messages.append(HumanMessage(
                        content=(
                            "Retry. Return ONLY valid JSON with keys: "
                            "'answer' (string, 3-4 sentences). "
                            "Use only values from the evidence above."
                        )
                    ))

        return ForensicReport(
            answer="Data not available in current dataset."
        )


# ── Evidence parser ────────────────────────────────────────────────────────────

def _parse_evidence(raw: str, label: str) -> EvidencePayload:
    """
    Extracts EvidencePayload from agent output string.
    Falls back to wrapping the raw string if JSON parse fails.
    """
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
    try:
        data = json.loads(cleaned)
        return EvidencePayload(evidence=data.get("evidence", cleaned))
    except Exception:
        logger.debug(f"[{label}Agent] Non-JSON output, wrapping.")
        return EvidencePayload(evidence=cleaned if cleaned else "No evidence retrieved.")
