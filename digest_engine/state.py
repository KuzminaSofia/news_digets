"""Persistent dedup state.

The pipeline's primary freshness mechanism is the time window (``filters.lookback_hours``).
A StateStore is an *optional* second layer: it remembers which item hashes were already
delivered, so an item is never repeated even if it stays in a feed across runs.

This is intentionally a small interface so other backends (SQLite, Redis, S3) can be
added later without touching the pipeline. ``none`` is the default and stores nothing.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path

from digest_engine.config import StateConfig

logger = logging.getLogger(__name__)


class StateStore(ABC):
    @abstractmethod
    def seen(self, content_hash: str) -> bool: ...

    @abstractmethod
    def mark(self, content_hash: str) -> None: ...

    def commit(self) -> None:
        """Persist any pending changes. No-op for in-memory backends."""


class NoopStateStore(StateStore):
    """Stores nothing; every item is treated as unseen. Default backend."""

    def seen(self, content_hash: str) -> bool:
        return False

    def mark(self, content_hash: str) -> None:
        return None


class JsonStateStore(StateStore):
    """Hash -> ISO timestamp map persisted as JSON. Old entries are pruned on load."""

    def __init__(self, path: str | Path, retention_days: int) -> None:
        self.path = Path(path)
        self.retention = timedelta(days=retention_days)
        self._data: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("could not read state file %s: %s", self.path, exc)
            return {}
        cutoff = datetime.now(timezone.utc) - self.retention
        return {
            h: ts
            for h, ts in data.items()
            if _parse(ts) is None or _parse(ts) >= cutoff
        }

    def seen(self, content_hash: str) -> bool:
        return content_hash in self._data

    def mark(self, content_hash: str) -> None:
        self._data[content_hash] = datetime.now(timezone.utc).isoformat()

    def commit(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("state committed: %d hashes -> %s", len(self._data), self.path)


def _parse(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def build_state_store(config: StateConfig) -> StateStore:
    if config.type == "json":
        return JsonStateStore(config.path, config.retention_days)
    return NoopStateStore()
