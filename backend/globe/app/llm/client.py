from functools import lru_cache
from typing import Any, Dict, List, Optional, cast

from groq import AsyncGroq

from app.config import get_settings

# Groq SDK appends the OpenAI-compatible route segment internally.
# Keep this at host root to avoid /openai/v1/openai/v1 duplication.
_GROQ_BASE_URL = "https://api.groq.com"


def _normalize_model(model_name: str) -> str:
    # Accept either "llama-..." or "groq/llama-..." and always send the raw model ID.
    if "/" in model_name:
        provider, raw = model_name.split("/", 1)
        if provider.strip().lower() == "groq" and raw:
            return raw
    return model_name


@lru_cache(maxsize=1)
def get_groq_client() -> AsyncGroq:
    settings = get_settings()
    return AsyncGroq(
        api_key=settings.GROQ_API_KEY,
        base_url=_GROQ_BASE_URL,
    )


async def request_chat_completion(
    *,
    messages: List[Dict[str, str]],
    model: str,
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
) -> str:
    client = get_groq_client()
    response = await client.chat.completions.create(
        model=_normalize_model(model),
        messages=cast(Any, messages),
        temperature=temperature,
        max_tokens=max_tokens,
    )
    content = response.choices[0].message.content if response.choices else ""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return str(content)
