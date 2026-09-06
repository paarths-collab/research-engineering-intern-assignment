"""
llm_models.py
-------------
One place that resolves Groq model identifiers for the two call styles used
across the backend.

LiteLLM needs a provider-qualified id (``groq/openai/gpt-oss-20b``) to route to
Groq. The Groq SDK, langchain's ChatGroq, and raw REST calls need the bare id
(``openai/gpt-oss-20b``).

The default model id contains a slash of its own, so a plain "does it contain a
slash" check reads ``openai/gpt-oss-20b`` as an *OpenAI* model and LiteLLM sends
the Groq key to OpenAI. Anchor on the ``groq/`` prefix instead.
"""

from __future__ import annotations

import os

DEFAULT_MODEL = "openai/gpt-oss-20b"
_PREFIX = "groq/"


def _first_set(env_vars: tuple[str, ...]) -> str | None:
    for name in env_vars:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def litellm_model(*env_vars: str, default: str = DEFAULT_MODEL) -> str:
    """Provider-qualified id for LiteLLM, e.g. ``groq/openai/gpt-oss-20b``."""
    raw = _first_set(env_vars) or default
    return raw if raw.startswith(_PREFIX) else f"{_PREFIX}{raw}"


def groq_model(*env_vars: str, default: str = DEFAULT_MODEL) -> str:
    """Bare id for the Groq SDK / ChatGroq / REST, e.g. ``openai/gpt-oss-20b``."""
    raw = _first_set(env_vars) or default
    return raw[len(_PREFIX):] if raw.startswith(_PREFIX) else raw
