"""
agent/llm_client.py
~~~~~~~~~~~~~~~~~~~
Unified LLM client that supports multiple providers (Groq, GitHub Models).

All AI calls go through `LLMClient.call()` — the rest of the codebase
never touches provider-specific details.
"""

import logging
from typing import List, Dict

import requests
from groq import Groq

from agent.config import (
    AI_PROVIDER,
    MODEL_ID,
    GROQ_API_KEY,
    GITHUB_MODEL,
    AI_GITHUB_TOKEN,
    GITHUB_MODELS_URL,
)

logger = logging.getLogger("cloud-agent.llm")


class LLMClient:
    """Provider-agnostic LLM caller."""

    def __init__(self) -> None:
        self._provider = AI_PROVIDER
        if self._provider == "GROQ":
            self._groq = Groq(api_key=GROQ_API_KEY)
        else:
            self._groq = None

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def call(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
    ) -> str:
        """Send *messages* to the configured provider and return the reply text."""
        logger.debug(
            f"LLM call  provider={self._provider}  msgs={len(messages)}  temp={temperature}"
        )
        try:
            if self._provider == "GITHUB":
                return self._call_github(messages, temperature)
            return self._call_groq(messages, temperature)
        except Exception as e:
            logger.error(f"LLM call failed: {e}", exc_info=True)
            return ""

    # ------------------------------------------------------------------
    # Private provider implementations
    # ------------------------------------------------------------------
    def _call_groq(
        self, messages: List[Dict[str, str]], temperature: float
    ) -> str:
        res = self._groq.chat.completions.create(
            model=MODEL_ID,
            temperature=temperature,
            messages=messages,
        )
        result = (res.choices[0].message.content or "").strip()
        logger.debug("Groq response received.")
        return result

    def _call_github(
        self, messages: List[Dict[str, str]], temperature: float
    ) -> str:
        payload: dict = {
            "messages": messages,
            "model": GITHUB_MODEL,
            "max_tokens": 4096,
        }
        # "o-series" models use max_completion_tokens instead
        if GITHUB_MODEL.startswith("o"):
            payload["max_completion_tokens"] = payload.pop("max_tokens")
        else:
            payload["temperature"] = temperature

        r = requests.post(
            GITHUB_MODELS_URL,
            headers={
                "Authorization": f"Bearer {AI_GITHUB_TOKEN}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        if r.status_code != 200:
            logger.error(f"GitHub Models API {r.status_code}: {r.text}")
            return ""

        result = r.json()["choices"][0]["message"]["content"]
        logger.debug("GitHub Models response received.")
        return result
