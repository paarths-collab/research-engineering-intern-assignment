"""
rate_limit_handler.py
─────────────────────
Drop-in wrapper for your CrewAI + LiteLLM/Groq pipeline.
• Runs agents SEQUENTIALLY (one at a time)
• Rate limit / disconnect errors  → wait 60s and retry
• Context overflow (None/empty)   → return graceful fallback JSON immediately
  (Retrying on context overflow just repeats the same bloated context loop)
• Graceful Ctrl+C — no "interpreter shutdown" cascade
"""

import time
import logging
import signal
import sys
from functools import wraps
from typing import Callable, Any

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

# ── Hard rate limit signals → RETRY after 60s ────────────────────────────────
RATE_LIMIT_SIGNALS = [
    "rate limit",
    "ratelimit",
    "rate_limit",
    "429",
    "too many requests",
    "quota exceeded",
    "tokens per minute",
    "requests per minute",
    "server disconnected",
    "server disconnected without sending a response",
]

# ── Context overflow signals → DON'T retry, return fallback ──────────────────
# These happen when the agent runs too many tool calls and bloats the context.
# Retrying crew.kickoff() just replays the same bloated conversation → same None.
CONTEXT_OVERFLOW_SIGNALS = [
    "none or empty",
    "invalid response from llm call",
    "received none or empty response",
    "empty response",
]

# Fallback returned when agent has context overflow (it got the data but couldn't conclude)
FALLBACK_JSON = (
    '{"answer": "The agent gathered data but hit a context limit before writing a conclusion. '
    'This happens when too many tool calls are made in one query. '
    'Please try a more focused question — e.g. target one cluster ID or one subreddit at a time.", '
    '"follow_up": ['
    '"Can you narrow the query to a specific subreddit or date range?", '
    '"Try asking about a single cluster ID directly."]}'
)

WAIT_SECONDS = 60
MAX_RETRIES  = 5


def is_rate_limit_error(exc: Exception) -> bool:
    """True if the error is a hard rate limit or connection drop — safe to retry."""
    msg = str(exc).lower()
    return any(sig in msg for sig in RATE_LIMIT_SIGNALS)


def is_context_overflow_error(exc: Exception) -> bool:
    """True if LLM returned None/empty — context too large, do NOT retry."""
    msg = str(exc).lower()
    return any(sig in msg for sig in CONTEXT_OVERFLOW_SIGNALS)


# ── Core retry decorator ──────────────────────────────────────────────────────
def with_rate_limit_retry(max_retries: int = MAX_RETRIES, wait: int = WAIT_SECONDS):
    """
    Decorator: retries a function on rate-limit errors only.
    Context overflow errors return FALLBACK_JSON immediately.
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs) -> Any:
            for attempt in range(1, max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    if is_context_overflow_error(exc):
                        logger.warning(
                            f"⚠️  Context overflow detected — agent over-queried. "
                            f"Returning fallback instead of retrying.\n   {exc}"
                        )
                        return FALLBACK_JSON
                    elif is_rate_limit_error(exc):
                        if attempt < max_retries:
                            logger.warning(
                                f"⏳ Rate limit hit (attempt {attempt}/{max_retries}). "
                                f"Waiting {wait}s…\n   {exc}"
                            )
                            time.sleep(wait)
                        else:
                            logger.error(f"❌ Rate limit persists after {max_retries} retries.")
                            raise
                    else:
                        raise
        return wrapper
    return decorator


# ── Sequential pipeline runner ────────────────────────────────────────────────
class SequentialAgentRunner:
    """
    Runs CrewAI agents one after another with smart error handling:
    - Rate limit  → wait 60s, retry (up to max_retries)
    - None/empty  → return fallback JSON immediately (no retry loop)
    - Ctrl+C      → clean shutdown (no interpreter crash)
    """

    def __init__(self, wait_seconds: int = WAIT_SECONDS, max_retries: int = MAX_RETRIES):
        self.wait    = wait_seconds
        self.retries = max_retries
        self._setup_signal_handler()

    def _setup_signal_handler(self):
        def _handler(sig, frame):
            logger.info("\n🛑 Interrupted by user. Shutting down cleanly…")
            sys.exit(0)
        try:
            signal.signal(signal.SIGINT, _handler)
            if hasattr(signal, "SIGTERM"):
                signal.signal(signal.SIGTERM, _handler)
        except ValueError:
            pass

    def _run_one(self, agent_fn: Callable, agent_name: str, *args, **kwargs) -> Any:
        for attempt in range(1, self.retries + 1):
            try:
                logger.info(f"▶️  Running [{agent_name}] — attempt {attempt}/{self.retries}")
                result = agent_fn(*args, **kwargs)
                logger.info(f"✅  [{agent_name}] completed successfully.")
                return result

            except Exception as exc:
                # ── Context overflow: agent got data but LLM dropped mid-conclusion ──
                if is_context_overflow_error(exc):
                    logger.warning(
                        f"⚠️  [{agent_name}] context overflow — agent over-queried Groq.\n"
                        f"   NOT retrying (would loop). Returning graceful fallback.\n"
                        f"   Fix: add max_iter=5 to your Task and simplify the query."
                    )
                    return FALLBACK_JSON

                # ── Hard rate limit: wait and retry ───────────────────────────────
                elif is_rate_limit_error(exc):
                    wait_time = 65 if "tokens per minute" in str(exc).lower() else self.wait
                    if attempt < self.retries:
                        logger.warning(
                            f"⏳ [{agent_name}] rate limit hit (attempt {attempt}/{self.retries}). "
                            f"Waiting {wait_time}s…\n   {exc}"
                        )
                        self._countdown(wait_time)
                    else:
                        logger.error(f"❌ [{agent_name}] rate limit after {self.retries} retries.")
                        raise

                # ── Unknown error: surface immediately ────────────────────────────
                else:
                    logger.error(f"❌ [{agent_name}] unexpected error: {exc}")
                    raise

    def _countdown(self, seconds: int):
        for remaining in range(seconds, 0, -10):
            logger.info(f"   ⏰ Retrying in {remaining}s…")
            time.sleep(min(10, remaining))

    def run(self, agents: list) -> list:
        """
        agents: list of dicts:
            [
                {"name": "Forensic Detective", "fn": crew.kickoff, "kwargs": {"inputs": {...}}},
            ]
        Returns list of results (fallback JSON string if context overflow).
        """
        results = []
        total   = len(agents)

        for idx, agent_spec in enumerate(agents, start=1):
            if isinstance(agent_spec, dict):
                name   = agent_spec.get("name", f"Agent-{idx}")
                fn     = agent_spec["fn"]
                args   = agent_spec.get("args", ())
                kwargs = agent_spec.get("kwargs", {})
            else:
                name, fn = agent_spec[0], agent_spec[1]
                args     = agent_spec[2] if len(agent_spec) > 2 else ()
                kwargs   = agent_spec[3] if len(agent_spec) > 3 else {}

            logger.info(f"\n{'='*55}")
            logger.info(f"  AGENT {idx}/{total}: {name}")
            logger.info(f"{'='*55}")

            result = self._run_one(fn, name, *args, **kwargs)
            results.append(result)

        logger.info("\n🎉 All agents completed.")
        return results


# ── CrewAI convenience wrapper ────────────────────────────────────────────────
def run_crew_sequentially(crew, inputs: dict = None,
                          wait_seconds: int = WAIT_SECONDS,
                          max_retries:  int = MAX_RETRIES) -> Any:
    runner = SequentialAgentRunner(wait_seconds=wait_seconds, max_retries=max_retries)
    return runner._run_one(
        lambda: crew.kickoff(inputs=inputs) if inputs else crew.kickoff(),
        agent_name="CrewAI Pipeline"
    )

if __name__ == "__main__":
    call_count = {"n": 0}

    def mock_rate_limit_then_succeed():
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise Exception("GroqException - rate limit 429")
        return '{"answer": "cluster 12.0 found in r/worldpolitics", "follow_up": []}'

    def mock_context_overflow():
        raise Exception("Invalid response from LLM call - None or empty.")

    runner = SequentialAgentRunner(wait_seconds=3, max_retries=4)

    results = runner.run([
        {"name": "Forensic Detective (rate limit test)", "fn": mock_rate_limit_then_succeed},
        {"name": "Summary Agent (context overflow test)", "fn": mock_context_overflow},
    ])

    print("\n── Final Results ──")
    for i, r in enumerate(results, 1):
        print(f"  Agent {i}: {r}")
