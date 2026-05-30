"""LLM provider abstraction + registry.

The pipeline only ever calls ``LLMProvider.chat(...)``. Swapping OpenRouter for OpenAI,
Anthropic, a local model, etc. means writing one adapter and registering it; the config's
``llm.provider`` selects which one is used.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Callable

from digest_engine.config import LLMConfig

_REGISTRY: dict[str, type["LLMProvider"]] = {}


def register_provider(name: str) -> Callable[[type["LLMProvider"]], type["LLMProvider"]]:
    def decorator(cls: type["LLMProvider"]) -> type["LLMProvider"]:
        _REGISTRY[name] = cls
        return cls

    return decorator


class LLMError(RuntimeError):
    """Raised when the provider cannot return a completion."""


class LLMProvider(ABC):
    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def _require_api_key(self) -> str:
        key = os.environ.get(self.config.api_key_env, "")
        if not key:
            raise LLMError(
                f"missing API key: set the {self.config.api_key_env} environment variable"
            )
        return key

    @abstractmethod
    def chat(self, system: str, user: str) -> str:
        """Return the assistant's text response for a single-turn system+user prompt."""


def build_provider(config: LLMConfig) -> LLMProvider:
    try:
        cls = _REGISTRY[config.provider]
    except KeyError as exc:
        raise ValueError(
            f"unknown llm provider '{config.provider}'. Registered: {sorted(_REGISTRY)}"
        ) from exc
    return cls(config)
