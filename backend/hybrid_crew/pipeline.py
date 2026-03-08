"""
hybrid_crew/pipeline.py
------------------------
Full Research-Style (Option B) pipeline.

Flow:
  Step 1: PlannerAgent   — decompose query into sub-tasks
  Step 2: RouterAgent    — decide execution mode (sql_only / vector_only / hybrid)
  Step 3: SpecialistCrew — run SQL and/or Vector agents
  Step 4: ForensicAgent  — synthesise evidence into ForensicReport
  Step 5: ReviewerAgent  — ground-check and correct the ForensicReport
  Step 6: Validator      — pure-Python grounding validation
  Step 7: Narrator       — LLM polish into clean prose

All agents are bounded (no recursive loops). Guardrails at tool layer.
"""

import os
import re
import sys
import io
import time
import asyncio
import logging
import concurrent.futures
from typing import Optional
from pathlib import Path

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain.schema import SystemMessage, HumanMessage

# ── Force UTF-8 on Windows ─────────────────────────────────────────────────────
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Load env ───────────────────────────────────────────────────────────────────
_env_path = Path(r"C:\Users\Paarth\Coding\simppl\research-engineering-intern-assignment\backend\.env")
load_dotenv(dotenv_path=_env_path)
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "")

# ── Imports from hybrid (shared tools/constants) and hybrid_crew (new agents) ──
from hybrid.constants import VALID_SUBREDDITS, INTERNAL_KEY_COLUMNS
from hybrid.validation_utils import parse_evidence, metric_value_grounded
from hybrid_crew.agents import (
    PlannerAgent, RouterAgent, SQLAgent, VectorAgent,
    ForensicAgent, ReviewerAgent,
    EvidencePayload, ForensicReport,
)
from hybrid_crew.crew_config import SpecialistCrew

logger = logging.getLogger(__name__)

# ── Timeout config ─────────────────────────────────────────────────────────────
_SQL_TIMEOUT    = int(os.getenv("SQL_AGENT_TIMEOUT",    "90"))
_VECTOR_TIMEOUT = int(os.getenv("VECTOR_AGENT_TIMEOUT", "60"))
_RATE_LIMIT_WAIT = int(os.getenv("RATE_LIMIT_WAIT_SECONDS", "60"))

_RATE_LIMIT_SIGNALS = (
    "rate limit", "ratelimit", "rate_limit", "429",
    "too many requests", "quota exceeded",
    "tokens per minute", "requests per minute",
    "server disconnected",
)

# ── Shared LLM instance ────────────────────────────────────────────────────────
_llm = ChatGroq(
    api_key=os.getenv("GROQ_API_KEY"),
    model=os.getenv("HIGH_MODEL", "llama-3.3-70b-versatile").replace("groq/", ""),
    temperature=0,
)

# ── Agent singletons ───────────────────────────────────────────────────────────
_planner  = PlannerAgent(_llm)
_router   = RouterAgent(_llm)
_sql      = SQLAgent(_llm)
_vector   = VectorAgent(_llm)
_forensic = ForensicAgent(_llm)
_reviewer = ReviewerAgent(_llm)
_crew     = SpecialistCrew(_sql, _vector)

# ── Fallback payloads ──────────────────────────────────────────────────────────
_SQL_TIMEOUT_PAYLOAD    = EvidencePayload(evidence="SQL agent timed out. No data retrieved.")
_VECTOR_TIMEOUT_PAYLOAD = EvidencePayload(evidence="Vector agent timed out. No data retrieved.")


# ═══════════════════════════════════════════════════════════════════════════════
# Rate-limit helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(sig in msg for sig in _RATE_LIMIT_SIGNALS)


def _llm_invoke_with_retry(messages: list, max_retries: int = 3) -> str:
    for attempt in range(1, max_retries + 1):
        try:
            resp = _llm.invoke(messages)
            return resp.content.strip() if hasattr(resp, "content") else ""
        except Exception as exc:
            if _is_rate_limit(exc) and attempt < max_retries:
                logger.warning(
                    f"[LLM] Rate limit hit (attempt {attempt}/{max_retries}). "
                    f"Waiting {_RATE_LIMIT_WAIT}s…"
                )
                time.sleep(_RATE_LIMIT_WAIT)
            else:
                raise
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# Narrator
# ═══════════════════════════════════════════════════════════════════════════════

_NARRATOR_SYSTEM = (
    "You are a concise, professional data analyst. "
    "Given a raw factual answer, rewrite it as 2-3 clear, natural English sentences. "
    "Keep ALL numbers and names exactly as given. "
    "Do NOT add any information not in the input. "
    "Do NOT use bullet points or markdown. "
    "Return ONLY the polished prose — nothing else."
)

def _narrate(raw_answer: str) -> str:
    try:
        narrated = _llm_invoke_with_retry([
            SystemMessage(content=_NARRATOR_SYSTEM),
            HumanMessage(content=raw_answer),
        ])
        return narrated if narrated else raw_answer
    except Exception as exc:
        logger.warning(f"[Narrator] Failed, returning original: {exc}")
        return raw_answer


# ═══════════════════════════════════════════════════════════════════════════════
# Validator (pure Python, no LLM cost)
# ═══════════════════════════════════════════════════════════════════════════════

class ValidationResult:
    def __init__(self, passed: bool, violations: list):
        self.passed     = passed
        self.violations = violations


def _build_evidence_text(
    sql_evidence: Optional[EvidencePayload],
    vector_evidence: Optional[EvidencePayload],
) -> str:
    parts = []
    if sql_evidence:    parts.append(sql_evidence.evidence)
    if vector_evidence: parts.append(vector_evidence.evidence)
    return "\n".join(parts)


def validate(
    answer: str,
    sql_evidence: Optional[EvidencePayload],
    vector_evidence: Optional[EvidencePayload],
) -> ValidationResult:
    evidence_text = _build_evidence_text(sql_evidence, vector_evidence)
    violations: list[str] = []

    # 1. Subreddit validity
    mentioned_subs = set()
    for m in re.finditer(r"r/([A-Za-z]+)", answer):
        mentioned_subs.add(m.group(1))
    for word in re.findall(r"\b[A-Za-z]{4,30}\b", answer):
        if word in VALID_SUBREDDITS:
            mentioned_subs.add(word)
    invalid = mentioned_subs - VALID_SUBREDDITS
    if invalid:
        violations.append(f"Subreddits not in dataset: {invalid}")

    # 2. Number grounding
    if evidence_text:
        answer_nums   = set(re.findall(r"\b\d{2,}\b", answer))
        evidence_nums = set(re.findall(r"\b\d{2,}\b", evidence_text))
        ungrounded = answer_nums - evidence_nums
        if ungrounded:
            violations.append(f"Numbers not in evidence: {ungrounded}")

    # 3. Internal key leak
    for key in INTERNAL_KEY_COLUMNS:
        if re.search(rf"\b{re.escape(key)}\b", answer, re.IGNORECASE):
            violations.append(f"Internal key '{key}' leaked into answer.")

    # 4. Date grounding
    answer_dates   = set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", answer))
    evidence_dates = set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", evidence_text))
    ungrounded_dates = answer_dates - evidence_dates
    if ungrounded_dates and evidence_text:
        violations.append(f"Dates not in evidence: {ungrounded_dates}")

    # 5. Fabricated percentages
    answer_pcts   = set(re.findall(r"\b\d+(?:\.\d+)?%", answer))
    evidence_pcts = set(re.findall(r"\b\d+(?:\.\d+)?%", evidence_text))
    fake_pcts = answer_pcts - evidence_pcts
    if fake_pcts and evidence_text:
        violations.append(f"Percentages not in evidence: {fake_pcts}")

    # 6. Context-aware metric grounding
    if sql_evidence and sql_evidence.evidence:
        rows = parse_evidence(sql_evidence.evidence)
        if rows:
            for col in rows[0].keys():
                if len(col) > 3:
                    pattern = rf"\b{re.escape(col)}\b\s*(?:of|is|was|:|=)?\s*([0-9,]+(?:\.[0-9]+)?)"
                    for m in re.finditer(pattern, answer, re.IGNORECASE):
                        val = m.group(1)
                        if not metric_value_grounded(col, val, rows):
                            violations.append(
                                f"Metric mismatch: '{col}' claimed as {val}, not found in evidence."
                            )

    return ValidationResult(passed=len(violations) == 0, violations=violations)


# ═══════════════════════════════════════════════════════════════════════════════
# Timed runner helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _run_timed_sql(query: str) -> EvidencePayload:
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_crew.run_sql, query)
            return future.result(timeout=_SQL_TIMEOUT)
    except concurrent.futures.TimeoutError:
        logger.error(f"[SQLAgent] Timed out after {_SQL_TIMEOUT}s")
        return _SQL_TIMEOUT_PAYLOAD
    except Exception as exc:
        logger.error(f"[SQLAgent] Unexpected error: {exc}")
        return EvidencePayload(evidence=f"SQL agent failed: {str(exc)[:200]}")


def _run_timed_vector(query: str) -> EvidencePayload:
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_crew.run_vector, query)
            return future.result(timeout=_VECTOR_TIMEOUT)
    except concurrent.futures.TimeoutError:
        logger.error(f"[VectorAgent] Timed out after {_VECTOR_TIMEOUT}s")
        return _VECTOR_TIMEOUT_PAYLOAD
    except Exception as exc:
        logger.error(f"[VectorAgent] Unexpected error: {exc}")
        return EvidencePayload(evidence=f"Vector agent failed: {str(exc)[:200]}")


# ═══════════════════════════════════════════════════════════════════════════════
# Main pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def run_pipeline_sync(user_query: str) -> dict:
    """
    Full research-style pipeline (synchronous).
    Returns:
    {
        "answer":      str,
        "route_used":  str,
        "plan":        dict,
        "timing":      dict,
        "validator":   {"passed": bool, "violations": list},
        "reviewer":    {"issues": list},
    }
    """
    t_total = time.perf_counter()
    timing: dict[str, float] = {}

    try:
        # ── Step 1: Planner ────────────────────────────────────────────────────
        t0 = time.perf_counter()
        plan = _planner.plan(user_query)
        timing["planner"] = round(time.perf_counter() - t0, 2)
        logger.info(f"[Pipeline] plan={plan.overall_strategy} | tasks={len(plan.sub_tasks)}")

        # ── Step 2: Router ─────────────────────────────────────────────────────
        t0 = time.perf_counter()
        route_decision = _router.decide(user_query, plan)
        route = route_decision.route
        timing["router"] = round(time.perf_counter() - t0, 2)
        logger.info(f"[Pipeline] route={route}")

        sql_evidence:    Optional[EvidencePayload] = None
        vector_evidence: Optional[EvidencePayload] = None

        # ── Step 3: Specialist Crew ─────────────────────────────────────────────
        t0 = time.perf_counter()
        if route == "sql_only":
            sql_evidence = _run_timed_sql(user_query)
        elif route == "vector_only":
            vector_evidence = _run_timed_vector(user_query)
        else:  # hybrid — parallel
            sql_evidence, vector_evidence = _crew.run_parallel(user_query)
        timing["retrieval"] = round(time.perf_counter() - t0, 2)

        # ── Step 4: Forensic Agent ─────────────────────────────────────────────
        t0 = time.perf_counter()
        forensic_report = _forensic.run(user_query, sql_evidence, vector_evidence)
        timing["forensic"] = round(time.perf_counter() - t0, 2)

        # ── Step 5: Reviewer Agent ─────────────────────────────────────────────
        t0 = time.perf_counter()
        review = _reviewer.review(user_query, forensic_report, sql_evidence, vector_evidence)
        timing["reviewer"] = round(time.perf_counter() - t0, 2)

        # Use reviewer's corrected answer
        final_answer = review.answer

        # ── Step 6: Pure-Python Validator ──────────────────────────────────────
        t0 = time.perf_counter()
        validation = validate(final_answer, sql_evidence, vector_evidence)
        timing["validator"] = round(time.perf_counter() - t0, 2)
        logger.info(f"[Validator] passed={validation.passed}")

        # ── Step 7: Narrator ────────────────────────────────────────────────────
        t0 = time.perf_counter()
        polished = _narrate(final_answer)
        timing["narrator"] = round(time.perf_counter() - t0, 2)

        timing["total"] = round(time.perf_counter() - t_total, 2)

        logger.info(
            f"[Pipeline] DONE | route={route} | timing={timing} | "
            f"validator_passed={validation.passed}"
        )

        return {
            "answer":     polished,
            "route_used": route,
            "plan": {
                "strategy": plan.overall_strategy,
                "tasks":    [{"type": t.type, "desc": t.description} for t in plan.sub_tasks],
            },
            "timing":   timing,
            "validator": {
                "passed":     validation.passed,
                "violations": validation.violations,
            },
            "reviewer": {
                "issues": review.issues,
            },
        }

    except Exception as exc:
        logger.exception(f"[Pipeline] Unhandled exception: {exc}")
        timing["total"] = round(time.perf_counter() - t_total, 2)
        return {
            "answer":     "An internal error occurred. Please try a more specific question.",
            "route_used": "error",
            "plan":       {},
            "timing":     timing,
            "validator":  {"passed": False, "violations": [str(exc)]},
            "reviewer":   {"issues": [str(exc)]},
        }
