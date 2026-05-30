"""RSS / Atom source backed by feedparser."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import struct_time

import feedparser

from digest_engine.models import RawItem
from digest_engine.sources.base import Source, register_source

logger = logging.getLogger(__name__)

# Polite UA; some feeds (and RSSHub mirrors) reject the default urllib agent.
_USER_AGENT = "digest-engine/0.1 (+https://github.com/digest-engine)"


def _to_datetime(parsed: struct_time | None) -> datetime | None:
    if parsed is None:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


@register_source("rss")
class RSSSource(Source):
    def fetch(self) -> list[RawItem]:
        feed = feedparser.parse(self.config.url, agent=_USER_AGENT)

        if getattr(feed, "bozo", 0) and not feed.entries:
            logger.warning(
                "source '%s' returned no entries (bozo=%s): %s",
                self.name,
                feed.bozo,
                getattr(feed, "bozo_exception", ""),
            )
            return []

        items: list[RawItem] = []
        for entry in feed.entries:
            link = entry.get("link", "").strip()
            title = entry.get("title", "").strip()
            if not title and not link:
                continue
            published = _to_datetime(
                entry.get("published_parsed") or entry.get("updated_parsed")
            )
            summary_html = entry.get("summary", "") or entry.get("description", "")
            items.append(
                RawItem(
                    source_name=self.name,
                    title=title,
                    link=link,
                    summary_html=summary_html,
                    published=published,
                    extra={"id": entry.get("id", link)},
                )
            )

        logger.info("source '%s' fetched %d entries", self.name, len(items))
        return items
