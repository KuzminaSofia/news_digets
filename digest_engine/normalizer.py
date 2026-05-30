"""Turn heterogeneous RawItems into clean, source-agnostic Items.

Responsibilities: strip HTML from summaries, collapse whitespace, truncate overly long
text, and canonicalize URLs (drop tracking params + fragments) so dedup is reliable.
"""

from __future__ import annotations

import logging
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from digest_engine.models import Item, RawItem

logger = logging.getLogger(__name__)

_MAX_SUMMARY_CHARS = 1000
_TRACKING_PREFIXES = ("utm_", "ref_", "fbclid", "gclid", "yclid", "igshid")


def _strip_html(html: str) -> str:
    if not html:
        return ""
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ")
    return " ".join(text.split())


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return url.strip()
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=False)
        if not any(k.lower().startswith(p) for p in _TRACKING_PREFIXES)
    ]
    cleaned = parsed._replace(query=urlencode(query), fragment="")
    return urlunparse(cleaned)


def normalize(raw: RawItem) -> Item | None:
    title = " ".join(raw.title.split())
    if not title:
        return None

    summary = _strip_html(raw.summary_html)
    if len(summary) > _MAX_SUMMARY_CHARS:
        summary = summary[:_MAX_SUMMARY_CHARS].rstrip() + "…"

    return Item(
        source_name=raw.source_name,
        title=title,
        url=canonicalize_url(raw.link),
        summary=summary,
        published=raw.published,
    )


def normalize_all(raw_items: list[RawItem]) -> list[Item]:
    items = [item for raw in raw_items if (item := normalize(raw)) is not None]
    logger.info("normalized %d/%d items", len(items), len(raw_items))
    return items
