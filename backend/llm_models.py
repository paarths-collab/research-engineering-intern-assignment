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

import logging
import os

logger = logging.getLogger("narrativesignal.llm_models")

DEFAULT_MODEL = "openai/gpt-oss-20b"
_PREFIX = "groq/"

# Groq no longer serves these. A stale env var naming one fails at call time
# with model_not_found, which reads as an outage rather than a config problem —
# so fall back to the default and say so loudly instead.
DECOMMISSIONED = frozenset({
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama2-70b-4096",
    "mixtral-8x7b-32768",
    "gemma-7b-it",
    "gemma-3-27b-it",
})


def _first_set(env_vars: tuple[str, ...]) -> str | None:
    for name in env_vars:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def _bare(model: str) -> str:
    return model[len(_PREFIX):] if model.startswith(_PREFIX) else model


def _resolve(env_vars: tuple[str, ...], default: str) -> str:
    """Bare, currently-served model id from the first env var that is set."""
    model = _bare(_first_set(env_vars) or default)
    if model in DECOMMISSIONED:
        replacement = _bare(default)
        if replacement in DECOMMISSIONED:
            replacement = DEFAULT_MODEL
        logger.warning(
            "Model %r is decommissioned on Groq (from %s); using %r instead.",
            model, " / ".join(env_vars) or "default", replacement,
        )
        model = replacement
    return model


def litellm_model(*env_vars: str, default: str = DEFAULT_MODEL) -> str:
    """Provider-qualified id for LiteLLM, e.g. ``groq/openai/gpt-oss-20b``."""
    return f"{_PREFIX}{_resolve(env_vars, default)}"


def groq_model(*env_vars: str, default: str = DEFAULT_MODEL) -> str:
    """Bare id for the Groq SDK / ChatGroq / REST, e.g. ``openai/gpt-oss-20b``."""
    return _resolve(env_vars, default)
