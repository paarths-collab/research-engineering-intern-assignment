"""
hybrid/pipeline.py
-------------------
Async orchestration pipeline with timeouts, fallbacks, and observability.

Fix 5: Deeper validator:
    - Subreddit validity
    - Number grounding
    - Internal key leak detection (narrative_id, cluster_id etc. in answer)
    - Date grounding (dates in answer must appear in evidence)
    - Fabricated percentage detection

Fix 6: Production hardening:
    - asyncio.wait_for(timeout=) per agent task
    - Safe fallback per agent (timeout -> EvidencePayload with error message)
    - Global exception wrapper in run_pipeline
    - Structured observability logging (route, agent times, validator result)
"""

import sys
import io
import os
import re
import time
import asyncio
import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from .validation_utils import parse_evidence, metric_value_grounded
from langchain_groq import ChatGroq

# Force UTF-8 on Windows
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

_env_path = Path(r"C:\Users\Paarth\Coding\simppl\research-engineering-intern-assignment\backend\.env")
load_dotenv(dotenv_path=_env_path)
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "")

from hybrid.orchestrator import OrchestratorAgent, RouteDecision
from hybrid.agents import SQLAgent, VectorAgent, ForensicAgent, ForensicReport, EvidencePayload
from hybrid.constants import VALID_SUBREDDITS, INTERNAL_KEY_COLUMNS

logger = logging.getLogger(__name__)

# ── Timeout config (seconds) ───────────────────────────────────────────────────
_SQL_TIMEOUT    = int(os.getenv("SQL_AGENT_TIMEOUT",    "90"))
_VECTOR_TIMEOUT = int(os.getenv("VECTOR_AGENT_TIMEOUT", "60"))

# ── Shared LLM instance ────────────────────────────────────────────────────────
_llm = ChatGroq(
    api_key=os.getenv("GROQ_API_KEY"),
    model=os.getenv("HIGH_MODEL", "llama-3.3-70b-versatile").replace("groq/", ""),
    temperature=0,
)

# ── Agent singletons ───────────────────────────────────────────────────────────
_orchestrator = OrchestratorAgent(_llm)
_sql_agent    = SQLAgent(_llm)
_vector_agent = VectorAgent(_llm)
_forensic     = ForensicAgent(_llm)

# ── Fallback payloads ──────────────────────────────────────────────────────────
_SQL_TIMEOUT_PAYLOAD    = EvidencePayload(evidence="SQL agent timed out. No data retrieved.")
_VECTOR_TIMEOUT_PAYLOAD = EvidencePayload(evidence="Vector agent timed out. No data retrieved.")
_SQL_ERROR_PAYLOAD      = EvidencePayload(evidence="SQL agent failed with an unexpected error.")
_VECTOR_ERROR_PAYLOAD   = EvidencePayload(evidence="Vector agent failed with an unexpected error.")


# ── Async wrappers with timeout + per-agent fallback ──────────────────────────

async def _run_sql(query: str) -> EvidencePayload:
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, _sql_agent.run, query),
            timeout=_SQL_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error(f"[SQLAgent] Timed out after {_SQL_TIMEOUT}s")
        return _SQL_TIMEOUT_PAYLOAD
    except Exception as exc:
        logger.error(f"[SQLAgent] Unexpected error: {exc}")
        return _SQL_ERROR_PAYLOAD


async def _run_vector(query: str) -> EvidencePayload:
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, _vector_agent.run, query),
            timeout=_VECTOR_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error(f"[VectorAgent] Timed out after {_VECTOR_TIMEOUT}s")
        return _VECTOR_TIMEOUT_PAYLOAD
    except Exception as exc:
        logger.error(f"[VectorAgent] Unexpected error: {exc}")
        return _VECTOR_ERROR_PAYLOAD


# ── Validator (Fix 5: deeper checks) ──────────────────────────────────────────

class ValidationResult:
    def __init__(self, passed: bool, violations: list[str]):
        self.passed     = passed
        self.violations = violations


def _build_evidence_text(
    sql_evidence: Optional[EvidencePayload],
    vector_evidence: Optional[EvidencePayload],
) -> str:
    parts = []
    if sql_evidence:
        parts.append(sql_evidence.evidence)
    if vector_evidence:
        parts.append(vector_evidence.evidence)
    return "\n".join(parts)


# Deprecated: parse_table moved to validation_utils.parse_evidence
# The function is retained here for reference but is no longer used.






def validate(
    report: ForensicReport,
    sql_evidence: Optional[EvidencePayload],
    vector_evidence: Optional[EvidencePayload],
) -> ValidationResult:
    """
    Pure-Python grounding check. No LLM cost.

    Checks:
    1. Subreddit validity            — every sub in answer must be in VALID_SUBREDDITS
    2. Number grounding              — 2+ digit numbers must appear in evidence
    3. Internal key leak             — narrative_id/cluster_id must not appear in answer text
    4. Date grounding                — YYYY-MM-DD dates in answer must appear in evidence
    5. Fabricated percentage         — percentages in answer must appear in evidence
    """
    answer        = report.answer
    evidence_text = _build_evidence_text(sql_evidence, vector_evidence)
    violations    = []

    # -- 1. Subreddit validity -------------------------------------------------
    mentioned_subs: set[str] = set()
    for m in re.finditer(r"r/([A-Za-z]+)", answer):
        mentioned_subs.add(m.group(1))
    for word in re.findall(r"\b[A-Za-z]{4,30}\b", answer):
        if word in VALID_SUBREDDITS:
            mentioned_subs.add(word)
    invalid_subs = mentioned_subs - VALID_SUBREDDITS
    if invalid_subs:
        violations.append(
            f"Subreddits not in dataset: {invalid_subs}. "
            f"Valid: {sorted(VALID_SUBREDDITS)}"
        )

    # -- 2. Number grounding (2+ digit integers) --------------------------------
    if evidence_text:
        answer_nums   = set(re.findall(r"\b\d{2,}\b", answer))
        evidence_nums = set(re.findall(r"\b\d{2,}\b", evidence_text))
        ungrounded    = answer_nums - evidence_nums
        if ungrounded:
            violations.append(
                f"Numbers in answer not found in evidence: {ungrounded}."
            )

    # -- 3. Internal key leak --------------------------------------------------
    for key in INTERNAL_KEY_COLUMNS:
        # Flag if the key appears in answer in a context suggesting it's a name
        # (i.e. not just "narrative_id column" or "narrative_id field")
        pattern = rf"\b{re.escape(key)}\b"
        if re.search(pattern, answer, re.IGNORECASE):
            violations.append(
                f"Internal key '{key}' appears in answer. "
                "Use representative_title or topic_label for narrative names."
            )

    # -- 4. Date grounding (YYYY-MM-DD) ----------------------------------------
    answer_dates   = set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", answer))
    evidence_dates = set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", evidence_text))
    ungrounded_dates = answer_dates - evidence_dates
    if ungrounded_dates and evidence_text:
        violations.append(
            f"Dates in answer not found in evidence: {ungrounded_dates}."
        )

    # -- 5. Fabricated percentage ----------------------------------------------
    answer_pcts   = set(re.findall(r"\b\d+(?:\.\d+)?%", answer))
    evidence_pcts = set(re.findall(r"\b\d+(?:\.\d+)?%", evidence_text))
    fake_pcts     = answer_pcts - evidence_pcts
    if fake_pcts and evidence_text:
        violations.append(
            f"Percentages in answer not found in evidence: {fake_pcts}. "
            "Do not compute or estimate percentages."
        )

    # -- 6. Context-aware metric checking (SQL only) ---------------------------
    if sql_evidence and sql_evidence.evidence:
        rows = parse_evidence(sql_evidence.evidence)
        if rows:
            headers = list(rows[0].keys())
            for col in headers:
                if len(col) > 3:  # skip tiny columns like 'id'
                    # Look for pattern: <col_name> [of|is|was|:|=] <number>
                    pattern = rf"\b{re.escape(col)}\b\s*(?:of|is|was|:|=)?\s*([0-9,]+(?:\.[0-9]+)?)"
                    for val_match in re.finditer(pattern, answer, re.IGNORECASE):
                        val = val_match.group(1)
                        if not metric_value_grounded(col, val, rows):
                            violations.append(
                                f"Metric mismatch: '{col}' claimed as {val}, "
                                "but this combination was not found in any single row of evidence."
                            )

    return ValidationResult(passed=len(violations) == 0, violations=violations)


def _build_correction_prompt(
    violations: list[str],
    query: str,
    sql_evidence: Optional[EvidencePayload],
    vector_evidence: Optional[EvidencePayload],
) -> str:
    sql_text    = sql_evidence.evidence    if sql_evidence    else "None"
    vector_text = vector_evidence.evidence if vector_evidence else "None"
    v_str       = "\n".join(f"  - {v}" for v in violations)
    return (
        f"ORIGINAL QUESTION: {query}\n\n"
        f"SQL EVIDENCE:\n{sql_text}\n\n"
        f"VECTOR EVIDENCE:\n{vector_text}\n\n"
        "YOUR PREVIOUS ANSWER HAD THESE VIOLATIONS:\n"
        f"{v_str}\n\n"
        "Rewrite the answer using ONLY values that appear verbatim in the evidence above. "
        "Do not add percentages, dates, or numbers not present in evidence. "
        "Return ONLY JSON: "
        '{"answer": "3-4 sentences"}'
    )


# ── Rate-limit helpers ─────────────────────────────────────────────────────────

_RATE_LIMIT_SIGNALS = (
    "rate limit", "ratelimit", "rate_limit", "429",
    "too many requests", "quota exceeded",
    "tokens per minute", "requests per minute",
    "server disconnected",
)
_RATE_LIMIT_WAIT = int(os.getenv("RATE_LIMIT_WAIT_SECONDS", "60"))

def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(sig in msg for sig in _RATE_LIMIT_SIGNALS)

def _llm_invoke_with_retry(messages: list, max_retries: int = 3) -> str:
    """Invoke _llm with automatic 60-s retry on rate-limit errors."""
    for attempt in range(1, max_retries + 1):
        try:
            resp = _llm.invoke(messages)
            return resp.content.strip() if hasattr(resp, "content") else ""
        except Exception as exc:
            if _is_rate_limit(exc) and attempt < max_retries:
                logger.warning(
                    f"[LLM] Rate limit hit (attempt {attempt}/{max_retries}). "
                    f"Waiting {_RATE_LIMIT_WAIT}s… ({exc})"
                )
                time.sleep(_RATE_LIMIT_WAIT)
            else:
                raise
    return ""


# ── Narrator (LLM sentence polishing) ─────────────────────────────────────────

_NARRATOR_SYSTEM = (
    "You are a concise, professional data analyst. "
    "Given a raw factual answer, rewrite it as 2-3 clear, natural English sentences. "
    "Keep ALL numbers and names exactly as given. "
    "Do NOT add any information not in the input. "
    "Do NOT use bullet points or markdown. "
    "Return ONLY the polished prose — nothing else."
)

def _narrate(raw_answer: str) -> str:
    """Pass the validated answer through a lightweight narrator LLM (with rate-limit retry)."""
    from langchain.schema import SystemMessage, HumanMessage
    try:
        narrated = _llm_invoke_with_retry([
            SystemMessage(content=_NARRATOR_SYSTEM),
            HumanMessage(content=raw_answer),
        ])
        return narrated if narrated else raw_answer
    except Exception as exc:
        logger.warning(f"[Narrator] Failed, returning original: {exc}")
        return raw_answer


# ── Main pipeline ──────────────────────────────────────────────────────────────

async def run_pipeline(user_query: str) -> dict:
    """
    Full async pipeline. Returns:
    {
        "answer":      str,
        "route_used":  str,
        "timing":      dict,
        "validator":   {"passed": bool, "violations": list}
    }
    """
    t_total = time.perf_counter()
    timing: dict[str, float] = {}

    try:
        # ── Step 1: Orchestrator (single LLM call, no timeout needed) ─────────
        t0 = time.perf_counter()
        routing: RouteDecision = _orchestrator.classify(user_query)
        route = routing.route
        timing["orchestrator"] = round(time.perf_counter() - t0, 2)
        logger.info(f"[Pipeline] route={route} | {routing.reason}")

        sql_evidence:    Optional[EvidencePayload] = None
        vector_evidence: Optional[EvidencePayload] = None

        # ── Step 2: Retrieval (parallel for hybrid) ───────────────────────────
        t0 = time.perf_counter()
        if route == "sql_only":
            sql_evidence = await _run_sql(user_query)
        elif route == "vector_only":
            vector_evidence = await _run_vector(user_query)
        else:  # hybrid — parallel
            sql_evidence, vector_evidence = await asyncio.gather(
                _run_sql(user_query),
                _run_vector(user_query),
            )
        timing["retrieval"] = round(time.perf_counter() - t0, 2)

        logger.info(
            f"[Pipeline] SQL evidence: {len(sql_evidence.evidence) if sql_evidence else 0} chars | "
            f"Vector evidence: {len(vector_evidence.evidence) if vector_evidence else 0} chars"
        )

        # ── Step 3: Forensic synthesis (no tools) ─────────────────────────────
        t0 = time.perf_counter()
        report = _forensic.run(user_query, sql_evidence, vector_evidence)
        timing["forensic"] = round(time.perf_counter() - t0, 2)

        # ── Step 4: Validator ─────────────────────────────────────────────────
        t0 = time.perf_counter()
        validation = validate(report, sql_evidence, vector_evidence)
        timing["validator"] = round(time.perf_counter() - t0, 2)
        logger.info(
            f"[Validator] passed={validation.passed} | "
            f"violations={validation.violations}"
        )

        # ── Step 5: One correction retry if needed ────────────────────────────
        if not validation.passed:
            logger.warning(f"[Validator] Violations: {validation.violations}")
            correction_prompt = _build_correction_prompt(
                validation.violations, user_query, sql_evidence, vector_evidence
            )
            t0 = time.perf_counter()
            report = _forensic.run(correction_prompt, sql_evidence, vector_evidence)
            timing["correction"] = round(time.perf_counter() - t0, 2)

            # Re-validate (no further retry — max 1 correction)
            validation = validate(report, sql_evidence, vector_evidence)
            logger.info(f"[Validator] After correction: passed={validation.passed}")

        timing["total"] = round(time.perf_counter() - t_total, 2)

        # ── Step 6: Narrator (clean sentence form) ────────────────────────────
        t0 = time.perf_counter()
        polished_answer = _narrate(report.answer)
        timing["narrator"] = round(time.perf_counter() - t0, 2)

        # ── Observability log ─────────────────────────────────────────────────
        logger.info(
            f"[Pipeline] DONE | route={route} | "
            f"timing={timing} | validator_passed={validation.passed}"
        )

        return {
            "answer":     polished_answer,
            "route_used": route,
            "timing":     timing,
            "validator":  {
                "passed":     validation.passed,
                "violations": validation.violations,
            },
        }

    except Exception as exc:
        # Global exception wrapper — never crash the API
        logger.exception(f"[Pipeline] Unhandled exception: {exc}")
        timing["total"] = round(time.perf_counter() - t_total, 2)
        return {
            "answer":     "An internal error occurred. Please try a more specific question.",
            "route_used": "error",
            "timing":     timing,
            "validator":  {"passed": False, "violations": [str(exc)]},
        }


# ── Sync wrapper for test scripts ──────────────────────────────────────────────

def run_pipeline_sync(user_query: str) -> dict:
    """Synchronous entry point for test scripts and CLI use."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, run_pipeline(user_query)).result()
        return loop.run_until_complete(run_pipeline(user_query))
    except RuntimeError:
        return asyncio.run(run_pipeline(user_query))
