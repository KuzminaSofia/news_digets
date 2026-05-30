"""Filtering + deduplication.

Order of operations:
  1. time-window filter  — keep only items published within ``lookback_hours``
  2. in-run dedup        — drop duplicate hashes seen earlier in this same run
  3. state-store dedup   — drop items already delivered in a previous run (optional)
  4. per-source cap      — limit items per source
  5. global cap          — limit total items (newest first)

Items without a publish date are kept (we can't prove they're stale) but sorted last.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from digest_engine.config import Config
from digest_engine.models import Item
from digest_engine.state import StateStore

logger = logging.getLogger(__name__)


def _within_window(item: Item, cutoff: datetime) -> bool:
    if item.published is None:
        return True
    published = item.published
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return published >= cutoff


def _sort_key(item: Item) -> datetime:
    if item.published is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    p = item.published
    return p if p.tzinfo else p.replace(tzinfo=timezone.utc)


def select_items(items: list[Item], config: Config, state: StateStore) -> list[Item]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.filters.lookback_hours)

    fresh = [i for i in items if _within_window(i, cutoff)]
    logger.info("time-window: %d/%d items within %dh", len(fresh), len(items),
                config.filters.lookback_hours)

    # Newest first so caps keep the most recent items.
    fresh.sort(key=_sort_key, reverse=True)

    per_source_cap: dict[str, int] = {}
    for s in config.sources:
        per_source_cap[s.name] = s.max_items or config.filters.max_items_per_source

    seen_hashes: set[str] = set()
    per_source_count: dict[str, int] = {}
    selected: list[Item] = []

    for item in fresh:
        h = item.content_hash
        if h in seen_hashes:
            continue
        seen_hashes.add(h)

        if state.seen(h):
            continue

        cap = per_source_cap.get(item.source_name, config.filters.max_items_per_source)
        if per_source_count.get(item.source_name, 0) >= cap:
            continue

        selected.append(item)
        per_source_count[item.source_name] = per_source_count.get(item.source_name, 0) + 1

        if len(selected) >= config.filters.max_items_total:
            break

    logger.info("selected %d items after dedup + caps", len(selected))
    return selected
