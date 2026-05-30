"""LLM providers. Importing this package registers all built-in adapters."""

from digest_engine.llm.base import LLMError, LLMProvider, build_provider, register_provider
from digest_engine.llm.openrouter import OpenRouterProvider

__all__ = [
    "LLMError",
    "LLMProvider",
    "build_provider",
    "register_provider",
    "OpenRouterProvider",
]
