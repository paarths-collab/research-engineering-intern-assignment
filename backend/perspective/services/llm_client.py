from __future__ import annotations

import json
import logging
import os
import time

import httpx

logger = logging.getLogger("perspective.llm")


class PerspectiveLLMClient:
    def __init__(self):
        self.api_key = os.getenv("PERSPECTIVE_LLM_API_KEY") or os.getenv("GROQ_API_KEY", "")
        base = os.getenv("PERSPECTIVE_LLM_BASE_URL", "https://api.groq.com/openai/v1")
        self.base_url = base.rstrip("/")
        model = os.getenv("PERSPECTIVE_LLM_MODEL") or os.getenv("LITE_MODEL") or "llama-3.1-8b-instant"
        self.model = model.replace("groq/", "")

    def generate(self, prompt: str) -> tuple[str, float]:
        if not self.api_key:
            raise RuntimeError("Missing LLM API key. Set PERSPECTIVE_LLM_API_KEY or GROQ_API_KEY.")

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You generate persona-grounded political reactions. "
                        "Follow output format exactly with Interpretation and Reaction sections."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 500,
        }

        t0 = time.perf_counter()
        with httpx.Client(timeout=40.0) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                content=json.dumps(payload),
            )
        elapsed = time.perf_counter() - t0

        if resp.status_code != 200:
            logger.error("Perspective LLM request failed: %s", resp.text[:1000])
            raise RuntimeError(f"Perspective LLM failed with status {resp.status_code}")

        content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        return content.strip(), elapsed
