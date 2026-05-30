from datetime import datetime, timezone

from digest_engine.config import Config
from digest_engine.delivery.telegram import chunk_message
from digest_engine.models import Digest, DigestEntry, Item
from digest_engine.render import render_telegram_html
from digest_engine.summarizer import _parse_response


def _cfg():
    return Config.model_validate(
        {"name": "t", "sources": [{"name": "S", "type": "rss", "url": "http://x"}]}
    )


def _digest():
    item = Item("S", "Title & stuff", "https://x.com/p?a=1", "Body <text>")
    entry = DigestEntry(item=item, headline="A <b>headline</b> & more",
                        summary="Why it matters", topics=["LLMs", "AI agents"])
    return Digest(title="My Digest", language="ru",
                  generated_at=datetime(2026, 5, 30, tzinfo=timezone.utc), entries=[entry])


def test_telegram_html_escapes_and_links():
    html = render_telegram_html(_digest(), _cfg())
    # Headline text is escaped...
    assert "A &lt;b&gt;headline&lt;/b&gt; &amp; more" in html
    # ...but wrapped in a real anchor tag.
    assert '<a href="https://x.com/p?a=1">' in html
    # Topics become safe hashtags.
    assert "#LLMs" in html and "#AI_agents" in html


def test_chunk_message_short():
    assert chunk_message("hello", 100) == ["hello"]


def test_chunk_message_splits_on_paragraphs():
    text = "\n\n".join(["A" * 50 for _ in range(5)])
    chunks = chunk_message(text, 120)
    assert all(len(c) <= 120 for c in chunks)
    assert len(chunks) > 1


def test_chunk_message_hard_splits_long_line():
    chunks = chunk_message("X" * 250, 100)
    assert all(len(c) <= 100 for c in chunks)
    assert "".join(chunks) == "X" * 250


def test_parse_response_valid():
    text = '```json\n[{"index": 0, "headline": "H", "summary": "S", "topics": ["t"]}]\n```'
    parsed = _parse_response(text, batch_len=1)
    assert parsed[0]["headline"] == "H"


def test_parse_response_invalid_returns_empty():
    assert _parse_response("not json", batch_len=2) == {}
