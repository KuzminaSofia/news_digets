"""Delivery channel abstraction + registry.

A channel knows how to render a Digest into its own format and push it out. Adding a new
channel (email, Slack, a webhook) means writing a subclass and registering it; the
config's ``delivery.type`` selects which one runs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from digest_engine.config import Config
from digest_engine.models import Digest

_REGISTRY: dict[str, type["DeliveryChannel"]] = {}


def register_channel(name: str) -> Callable[[type["DeliveryChannel"]], type["DeliveryChannel"]]:
    def decorator(cls: type["DeliveryChannel"]) -> type["DeliveryChannel"]:
        _REGISTRY[name] = cls
        return cls

    return decorator


class DeliveryError(RuntimeError):
    pass


class DeliveryChannel(ABC):
    def __init__(self, config: Config) -> None:
        self.config = config

    @abstractmethod
    def deliver(self, digest: Digest) -> None:
        """Push the digest to its destination."""


def build_channel(config: Config) -> DeliveryChannel:
    name = config.delivery.type
    try:
        cls = _REGISTRY[name]
    except KeyError as exc:
        raise ValueError(
            f"unknown delivery type '{name}'. Registered: {sorted(_REGISTRY)}"
        ) from exc
    return cls(config)
