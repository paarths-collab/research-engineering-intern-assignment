"""
hybrid_chatbot/prompting.py
--------------------------
Prompt template for the hybrid chatbot.
"""

from __future__ import annotations

from typing import Optional

SYSTEM_PROMPT = (
    "You are a concise narrative intelligence analyst. "
    "Use ONLY the provided SQL results and embedding context. "
    "If information is missing, say so explicitly and avoid guessing."
)


def build_user_prompt(
    question: str,
    sql_query: Optional[str],
    sql_results: Optional[str],
    vector_context: Optional[str],
    sql_status: Optional[str] = None,
    spike_query: bool = False,
) -> str:
    status_line = f"SQL STATUS: {sql_status}\n\n" if sql_status else ""
    sql_block = "None" if not sql_results else f"{status_line}SQL QUERY:\n{sql_query}\n\nSQL RESULTS:\n{sql_results}"
    vector_block = "None" if not vector_context else f"EMBEDDING CONTEXT:\n{vector_context}"
    spike_line = "SPIKE_QUERY: yes\n\n" if spike_query else "SPIKE_QUERY: no\n\n"

    return (
        f"QUESTION:\n{question}\n\n"
        f"{spike_line}{sql_block}\n\n"
        f"{vector_block}\n\n"
        "INSTRUCTIONS:\n"
        "- Use only the SQL results and embedding context above.\n"
        "- If both are present, combine them.\n"
        "- If SQL STATUS is error, say the SQL query failed and you cannot answer from SQL.\n"
        "- If SPIKE_QUERY is yes and SQL results are empty, say no spike was found in that window and do not infer causes.\n"
        "- If SPIKE_QUERY is no, do not mention spikes at all.\n"
        "- If the evidence is insufficient, state what is missing.\n"
        "- Keep the answer to 3-5 sentences."
    )
