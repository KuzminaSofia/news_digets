"""Configuration schema and loader.

The whole product is config-driven: to spin up a digest for someone else you copy a
YAML file under ``configs/`` and change values — no code edits required.

Secrets are NEVER stored in YAML. Config references *environment variable names*
(e.g. ``api_key_env: OPENROUTER_API_KEY``) and values are resolved at runtime. YAML
strings also support ``${ENV_VAR}`` interpolation for convenience.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


class SourceConfig(BaseModel):
    name: str
    type: str = "rss"
    url: str
    enabled: bool = True
    # Per-source cap; falls back to filters.max_items_per_source when None.
    max_items: int | None = None


class FiltersConfig(BaseModel):
    # Only items published within this window are considered "fresh".
    lookback_hours: int = Field(default=24, ge=1)
    max_items_per_source: int = Field(default=15, ge=1)
    # Hard cap on items sent to the LLM / into the digest.
    max_items_total: int = Field(default=40, ge=1)


class StateConfig(BaseModel):
    """Optional persistent dedup across runs. Default 'none' relies solely on the
    time window. 'json' remembers content hashes in a local file (commit it back or
    cache it in CI) so an item is never repeated even if it lingers in a feed."""

    type: Literal["none", "json"] = "none"
    path: str = "state/seen.json"
    # Forget hashes older than this so the file does not grow forever.
    retention_days: int = Field(default=14, ge=1)


class LLMConfig(BaseModel):
    provider: str = "openrouter"
    model: str = "openai/gpt-4o-mini"
    api_key_env: str = "OPENROUTER_API_KEY"
    base_url: str | None = None
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=400, ge=1)
    # Items are summarized in batches to control cost / latency.
    batch_size: int = Field(default=8, ge=1)


class TelegramOptions(BaseModel):
    bot_token_env: str = "TELEGRAM_BOT_TOKEN"
    chat_id_env: str = "TELEGRAM_CHAT_ID"
    # Telegram hard limit is 4096 chars; leave headroom.
    max_message_chars: int = Field(default=3800, ge=512, le=4096)
    disable_web_page_preview: bool = True


class DeliveryConfig(BaseModel):
    type: str = "telegram"
    telegram: TelegramOptions = Field(default_factory=TelegramOptions)
    # Also write each digest to disk (handy as a CI artifact / archive).
    save_to_dir: str | None = None


class RenderConfig(BaseModel):
    include_links: bool = True
    include_source: bool = True
    # Group entries by source in the output.
    group_by_source: bool = False


class Config(BaseModel):
    name: str
    language: str = "ru"
    timezone: str = "UTC"

    sources: list[SourceConfig]
    audience: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)

    filters: FiltersConfig = Field(default_factory=FiltersConfig)
    state: StateConfig = Field(default_factory=StateConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    delivery: DeliveryConfig = Field(default_factory=DeliveryConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)

    @field_validator("sources")
    @classmethod
    def _at_least_one_source(cls, v: list[SourceConfig]) -> list[SourceConfig]:
        if not v:
            raise ValueError("config must define at least one source")
        return v

    @property
    def enabled_sources(self) -> list[SourceConfig]:
        return [s for s in self.sources if s.enabled]


def _interpolate_env(value: Any) -> Any:
    """Recursively replace ${ENV_VAR} occurrences in strings with env values."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, list):
        return [_interpolate_env(v) for v in value]
    if isinstance(value, dict):
        return {k: _interpolate_env(v) for k, v in value.items()}
    return value


def load_config(path: str | Path) -> Config:
    """Load and validate a YAML config file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = _interpolate_env(raw)
    return Config.model_validate(raw)
