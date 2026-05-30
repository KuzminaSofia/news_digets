"""OpenRouter adapter.

OpenRouter exposes an OpenAI-compatible /chat/completions endpoint, so this same adapter
is trivially adaptable to OpenAI or any compatible gateway by changing ``base_url`` and
``api_key_env`` in the config.
"""

from __future__ import annotations

import logging
import os

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from digest_engine.config import LLMConfig
from digest_engine.llm.base import LLMError, LLMProvider, register_provider

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_TIMEOUT = httpx.Timeout(60.0)


@register_provider("openrouter")
class OpenRouterProvider(LLMProvider):
    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        self.base_url = (config.base_url or _DEFAULT_BASE_URL).rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._require_api_key()}",
            "Content-Type": "application/json",
        }
        # Optional attribution for OpenRouter dashboards.
        if referer := os.environ.get("OPENROUTER_REFERER"):
            headers["HTTP-Referer"] = referer
        if title := os.environ.get("OPENROUTER_TITLE"):
            headers["X-Title"] = title
        return headers

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def chat(self, system: str, user: str) -> str:
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # 4xx (other than 429) won't be fixed by retrying — surface immediately.
            if exc.response.status_code != 429 and 400 <= exc.response.status_code < 500:
                raise LLMError(
                    f"OpenRouter {exc.response.status_code}: {exc.response.text[:300]}"
                ) from exc
            raise

        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected OpenRouter response shape: {data}") from exc
