"""
hybrid_crew/crew_config.py
---------------------------
Crew definitions using sequential Process (no hierarchical recursion).

The Crew is only used for the specialist agents (SQL, Vector).
Planner, Router, Forensic, and Reviewer run outside the Crew,
giving us full control over the execution order.

Sequential process guarantees:
  - Agents run in the order they are listed.
  - Each agent's output is passed to the next.
  - No implicit re-planning loops.
  - No unbounded retries.
"""

import logging
from typing import Optional

from hybrid_crew.agents import (
    EvidencePayload,
    SQLAgent,
    VectorAgent,
)

logger = logging.getLogger(__name__)


class SpecialistCrew:
    """
    Thin sequential orchestrator for SQL + Vector specialists.
    Does NOT use CrewAI's built-in Crew class to avoid
    hidden hierarchical loops. All iteration caps are enforced
    inside each individual agent (SQL: max 3, Vector: max 2).
    """

    def __init__(self, sql_agent: SQLAgent, vector_agent: VectorAgent):
        self._sql    = sql_agent
        self._vector = vector_agent

    def run_sql(self, query: str) -> EvidencePayload:
        logger.info("[Crew] Running SQL specialist")
        return self._sql.run(query)

    def run_vector(self, query: str) -> EvidencePayload:
        logger.info("[Crew] Running Vector specialist")
        return self._vector.run(query)

    def run_parallel(self, query: str):
        """
        Run SQL and Vector agents.
        We use threading here to achieve parallel execution without
        requiring the CrewAI framework overhead.
        Returns (sql_evidence, vector_evidence).
        """
        import concurrent.futures
        logger.info("[Crew] Running SQL + Vector specialists in parallel")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            sql_future    = pool.submit(self._sql.run,    query)
            vector_future = pool.submit(self._vector.run, query)
            sql_ev    = sql_future.result()
            vector_ev = vector_future.result()
        return sql_ev, vector_ev
