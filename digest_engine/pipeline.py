"""End-to-end pipeline orchestration.

    fetch -> normalize -> select (window + dedup) -> summarize -> render -> deliver

Each stage is a small, independently testable function/class. The pipeline wires them
together and applies the run mode (dry-run skips delivery and does not persist state).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from digest_engine import dedup, normalizer
from digest_engine.config import Config
from digest_engine.delivery.base import build_channel
from digest_engine.llm.base import build_provider
from digest_engine.models import Digest, Item, RawItem
from digest_engine.render import build_digest, render_markdown
from digest_engine.sources.base import build_source
from digest_engine.state import build_state_store
from digest_engine.summarizer import summarize

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RunResult:
    digest: Digest
    delivered: bool
    markdown: str


def _fetch_all(config: Config) -> list[RawItem]:
    raw: list[RawItem] = []
    for source_cfg in config.enabled_sources:
        source = build_source(source_cfg)
        try:
            raw.extend(source.fetch())
        except Exception as exc:  # one bad source must not kill the run
            logger.exception("source '%s' failed: %s", source_cfg.name, exc)
    logger.info(
        "fetched %d raw items from %d sources", len(raw), len(config.enabled_sources)
    )
    return raw


def run(config: Config, *, dry_run: bool = False) -> RunResult:
    logger.info("starting digest '%s' (dry_run=%s)", config.name, dry_run)

    raw_items = _fetch_all(config)
    items: list[Item] = normalizer.normalize_all(raw_items)

    state = build_state_store(config.state)
    selected = dedup.select_items(items, config, state)

    if not selected:
        logger.info("no fresh items to report; nothing to deliver")
        digest = build_digest([], config)
        return RunResult(digest=digest, delivered=False, markdown=render_markdown(digest, config))

    provider = build_provider(config.llm)
    entries = summarize(selected, config, provider)
    digest = build_digest(entries, config)
    markdown = render_markdown(digest, config)

    if config.delivery.save_to_dir:
        _save_markdown(digest, markdown, config.delivery.save_to_dir)

    delivered = False
    if dry_run:
        logger.info("dry-run: skipping delivery and state commit")
    else:
        channel = build_channel(config)
        channel.deliver(digest)
        delivered = True
        for item in selected:
            state.mark(item.content_hash)
        state.commit()

    logger.info("done: %d entries, delivered=%s", len(entries), delivered)
    return RunResult(digest=digest, delivered=delivered, markdown=markdown)


def _save_markdown(digest: Digest, markdown: str, directory: str) -> None:
    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{digest.generated_at:%Y-%m-%d}.md"
    path = out_dir / fname
    path.write_text(markdown, encoding="utf-8")
    logger.info("saved digest to %s", path)
