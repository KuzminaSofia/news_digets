"""Summarize selected items into digest entries using an LLM.

Items are processed in batches (one LLM call per batch) for cost/latency control. The
model is asked to return strict JSON; if a batch fails or parses badly we fall back to
the item's own title/summary so the digest is always produced.
"""

from __future__ import annotations

import json
import logging
import re
from textwrap import shorten

from digest_engine.config import Config
from digest_engine.llm.base import LLMError, LLMProvider
from digest_engine.models import DigestEntry, Item

logger = logging.getLogger(__name__)

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _system_prompt(config: Config) -> str:
    audience = ", ".join(config.audience) or "general readers"
    topics = ", ".join(config.topics) or "anything noteworthy"
    return (
        "You are an editor producing a concise news digest.\n"
        f"Audience: {audience}.\n"
        f"Topics of interest: {topics}.\n"
        f"Write all output in this language (ISO code): {config.language}.\n\n"
        "For each numbered item you receive, produce:\n"
        '  - "headline": a punchy rewritten headline (max ~12 words)\n'
        '  - "summary": 1-2 sentences on why it matters to the audience\n'
        '  - "topics": 1-3 short topic tags from the topics of interest when relevant\n\n'
        "Respond with ONLY a JSON array, one object per item, each with keys "
        '"index" (int, matching the input), "headline", "summary", "topics" (array). '
        "No prose, no code fences."
    )


def _user_prompt(batch: list[Item]) -> str:
    lines = []
    for idx, item in enumerate(batch):
        body = shorten(item.summary, width=500, placeholder="…") if item.summary else ""
        lines.append(
            f"[{idx}] SOURCE: {item.source_name}\nTITLE: {item.title}\nTEXT: {body}".strip()
        )
    return "\n\n".join(lines)


def _parse_response(text: str, batch_len: int) -> dict[int, dict]:
    cleaned = _JSON_FENCE.sub("", text).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("could not parse LLM JSON; falling back for this batch")
        return {}
    if not isinstance(data, list):
        return {}
    out: dict[int, dict] = {}
    for obj in data:
        if isinstance(obj, dict) and isinstance(obj.get("index"), int):
            if 0 <= obj["index"] < batch_len:
                out[obj["index"]] = obj
    return out


def _entry_from(item: Item, parsed: dict | None) -> DigestEntry:
    if parsed:
        topics = parsed.get("topics") or []
        if not isinstance(topics, list):
            topics = [str(topics)]
        return DigestEntry(
            item=item,
            headline=str(parsed.get("headline") or item.title).strip(),
            summary=str(parsed.get("summary") or item.summary).strip(),
            topics=[str(t) for t in topics][:3],
        )
    # Fallback: use the raw item.
    return DigestEntry(
        item=item,
        headline=item.title,
        summary=shorten(item.summary, width=240, placeholder="…") if item.summary else "",
        topics=[],
    )


def summarize(items: list[Item], config: Config, provider: LLMProvider) -> list[DigestEntry]:
    entries: list[DigestEntry] = []
    batch_size = config.llm.batch_size

    for start in range(0, len(items), batch_size):
        batch = items[start : start + batch_size]
        parsed: dict[int, dict] = {}
        try:
            response = provider.chat(_system_prompt(config), _user_prompt(batch))
            parsed = _parse_response(response, len(batch))
        except LLMError as exc:
            logger.error("LLM batch failed, using fallback: %s", exc)

        for idx, item in enumerate(batch):
            entries.append(_entry_from(item, parsed.get(idx)))

    logger.info("summarized %d entries", len(entries))
    return entries
