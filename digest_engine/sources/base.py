"""Source abstraction + registry.

Adding a new source type (e.g. a website scraper, an API, a mailbox) means writing a
``Source`` subclass and decorating it with ``@register_source("type")``. The config's
``type`` field selects the implementation — no other code changes needed.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Callable

from digest_engine.config import SourceConfig
from digest_engine.models import RawItem

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, type["Source"]] = {}


def register_source(type_name: str) -> Callable[[type["Source"]], type["Source"]]:
    def decorator(cls: type["Source"]) -> type["Source"]:
        _REGISTRY[type_name] = cls
        return cls

    return decorator


class Source(ABC):
    def __init__(self, config: SourceConfig) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    @abstractmethod
    def fetch(self) -> list[RawItem]:
        """Return raw items from this source. Should not raise on network errors —
        log and return an empty list so one bad source can't break the whole run."""


def build_source(config: SourceConfig) -> Source:
    try:
        cls = _REGISTRY[config.type]
    except KeyError as exc:
        raise ValueError(
            f"unknown source type '{config.type}'. Registered: {sorted(_REGISTRY)}"
        ) from exc
    return cls(config)
