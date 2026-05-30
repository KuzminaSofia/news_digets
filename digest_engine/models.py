"""Domain models passed between pipeline stages.

These are plain dataclasses (not pydantic) because they are internal runtime objects,
created in hot loops, and never parsed from untrusted input. Config validation lives
in ``config.py``; this module is about data flowing through the pipeline.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class RawItem:
    """An entry exactly as returned by a source, before normalization."""

    source_name: str
    title: str
    link: str
    summary_html: str = ""
    published: datetime | None = None
    extra: dict = field(default_factory=dict)


@dataclass(slots=True)
class Item:
    """A normalized, source-agnostic news item."""

    source_name: str
    title: str
    url: str
    summary: str
    published: datetime | None = None

    @property
    def content_hash(self) -> str:
        """Stable identity used for dedup. Based on canonical URL, falling back to title."""
        basis = (self.url or self.title).strip().lower()
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class DigestEntry:
    """A summarized item ready for rendering."""

    item: Item
    headline: str
    summary: str
    topics: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Digest:
    """The full rendered-ready digest."""

    title: str
    language: str
    generated_at: datetime
    entries: list[DigestEntry] = field(default_factory=list)
    intro: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.entries
