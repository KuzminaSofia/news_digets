"""Delivery channels. Importing this package registers all built-in channels."""

from digest_engine.delivery.base import (
    DeliveryChannel,
    DeliveryError,
    build_channel,
    register_channel,
)
from digest_engine.delivery.telegram import TelegramChannel

__all__ = [
    "DeliveryChannel",
    "DeliveryError",
    "build_channel",
    "register_channel",
    "TelegramChannel",
]
