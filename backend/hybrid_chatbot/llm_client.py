"""
hybrid_chatbot/llm_client.py
---------------------------
Lightweight LLM client (Groq/OpenAI-compatible).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

import httpx

from .config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

logger = logging.getLogger("hybrid_chatbot.llm")


class LLMClient:
    def __init__(self):
        self.base_url = LLM_BASE_URL.rstrip("/")
        self.api_key = LLM_API_KEY
        self.model = LLM_MODEL

    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int = 400) -> tuple[str, float]:
        if not self.api_key:
            raise RuntimeError("LLM API key not configured. Set GROQ_API_KEY or HYBRID_LLM_API_KEY.")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }

        t0 = time.perf_counter()
        url = f"{self.base_url}/chat/completions"
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                content=json.dumps(payload),
            )
        elapsed = time.perf_counter() - t0
        if resp.status_code != 200:
            logger.error("LLM error: %s", resp.text[:2000])
            raise RuntimeError(f"LLM request failed: {resp.status_code}")

        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content.strip(), elapsed
