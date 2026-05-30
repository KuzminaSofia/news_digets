from datetime import datetime, timezone

from digest_engine.models import RawItem
from digest_engine.normalizer import canonicalize_url, normalize


def test_canonicalize_strips_tracking_and_fragment():
    url = "https://example.com/post?utm_source=tg&id=5&fbclid=x#section"
    assert canonicalize_url(url) == "https://example.com/post?id=5"


def test_canonicalize_empty():
    assert canonicalize_url("") == ""


def test_normalize_strips_html_and_keeps_fields():
    raw = RawItem(
        source_name="src",
        title="  Hello   World  ",
        link="https://x.com/a?utm_medium=rss",
        summary_html="<p>Some <b>bold</b> text</p>",
        published=datetime(2026, 5, 30, tzinfo=timezone.utc),
    )
    item = normalize(raw)
    assert item is not None
    assert item.title == "Hello World"
    assert item.summary == "Some bold text"
    assert item.url == "https://x.com/a"


def test_normalize_drops_titleless_item():
    raw = RawItem(source_name="s", title="   ", link="https://x.com")
    assert normalize(raw) is None


def test_content_hash_stable_and_url_based():
    a = normalize(RawItem("s1", "Title A", "https://x.com/p?utm_source=a"))
    b = normalize(RawItem("s2", "Different title", "https://x.com/p"))
    # Same canonical URL -> same hash regardless of source/title.
    assert a.content_hash == b.content_hash
