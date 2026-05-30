"""Assemble entries into a Digest and render it to output formats.

Two render targets:
  - Telegram HTML (parse_mode=HTML): supports <b>, <i>, <a>; everything else escaped.
  - Markdown: for the on-disk archive / dry-run preview.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from digest_engine.config import Config
from digest_engine.models import Digest, DigestEntry

logger = logging.getLogger(__name__)


def _now_in_tz(tz_name: str) -> datetime:
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        logger.warning("unknown timezone '%s', falling back to UTC", tz_name)
        tz = timezone.utc
    return datetime.now(tz)


def build_digest(entries: list[DigestEntry], config: Config) -> Digest:
    now = _now_in_tz(config.timezone)
    title = f"{config.name} — {now:%d.%m.%Y}"
    return Digest(
        title=title,
        language=config.language,
        generated_at=now,
        entries=entries,
    )


def _grouped(entries: list[DigestEntry]) -> dict[str, list[DigestEntry]]:
    groups: dict[str, list[DigestEntry]] = defaultdict(list)
    for e in entries:
        groups[e.item.source_name].append(e)
    return groups


def render_telegram_html(digest: Digest, config: Config) -> str:
    r = config.render
    parts: list[str] = [f"<b>{escape(digest.title)}</b>"]

    def render_entry(i: int, entry: DigestEntry) -> str:
        headline = escape(entry.headline)
        if r.include_links and entry.item.url:
            headline = f'<a href="{escape(entry.item.url, quote=True)}">{headline}</a>'
        block = [f"{i}. <b>{headline}</b>"]
        if entry.summary:
            block.append(escape(entry.summary))
        meta = []
        if r.include_source:
            meta.append(escape(entry.item.source_name))
        if entry.topics:
            meta.append(" ".join(f"#{escape(_tag(t))}" for t in entry.topics))
        if meta:
            block.append(f"<i>{' · '.join(meta)}</i>")
        return "\n".join(block)

    if r.group_by_source:
        n = 1
        for source, items in _grouped(digest.entries).items():
            parts.append(f"\n<b>— {escape(source)} —</b>")
            for entry in items:
                parts.append(render_entry(n, entry))
                n += 1
    else:
        for i, entry in enumerate(digest.entries, start=1):
            parts.append(render_entry(i, entry))

    return "\n\n".join(parts)


def render_markdown(digest: Digest, config: Config) -> str:
    lines = [f"# {digest.title}", ""]
    for i, entry in enumerate(digest.entries, start=1):
        if config.render.include_links and entry.item.url:
            lines.append(f"{i}. [{entry.headline}]({entry.item.url})")
        else:
            lines.append(f"{i}. {entry.headline}")
        if entry.summary:
            lines.append(f"   {entry.summary}")
        meta = []
        if config.render.include_source:
            meta.append(entry.item.source_name)
        if entry.topics:
            meta.append(" ".join(f"#{_tag(t)}" for t in entry.topics))
        if meta:
            lines.append(f"   _{' · '.join(meta)}_")
        lines.append("")
    return "\n".join(lines)


def _tag(text: str) -> str:
    """Make a topic safe as a hashtag: keep word chars, drop spaces/punct."""
    return "".join(ch for ch in text.replace(" ", "_") if ch.isalnum() or ch == "_")
