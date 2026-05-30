from datetime import datetime, timedelta, timezone

from digest_engine.config import Config
from digest_engine.dedup import select_items
from digest_engine.models import Item
from digest_engine.state import JsonStateStore, NoopStateStore


def _cfg(**overrides):
    base = {
        "name": "t",
        "sources": [{"name": "S1", "type": "rss", "url": "http://x"}],
        "filters": {"lookback_hours": 24, "max_items_per_source": 15, "max_items_total": 40},
    }
    base.update(overrides)
    return Config.model_validate(base)


def _item(title, url, hours_ago, source="S1"):
    return Item(
        source_name=source,
        title=title,
        url=url,
        summary="",
        published=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
    )


def test_time_window_filters_stale():
    cfg = _cfg()
    items = [_item("fresh", "http://a", 1), _item("stale", "http://b", 48)]
    out = select_items(items, cfg, NoopStateStore())
    assert [i.title for i in out] == ["fresh"]


def test_in_run_dedup_by_url():
    cfg = _cfg()
    items = [_item("a", "http://same", 1), _item("a-dupe", "http://same", 2)]
    out = select_items(items, cfg, NoopStateStore())
    assert len(out) == 1


def test_sorted_newest_first():
    cfg = _cfg()
    items = [_item("old", "http://a", 5), _item("new", "http://b", 1)]
    out = select_items(items, cfg, NoopStateStore())
    assert [i.title for i in out] == ["new", "old"]


def test_total_cap():
    cfg = _cfg(filters={"lookback_hours": 24, "max_items_per_source": 99, "max_items_total": 2})
    items = [_item(f"i{n}", f"http://{n}", n % 20) for n in range(10)]
    out = select_items(items, cfg, NoopStateStore())
    assert len(out) == 2


def test_per_source_cap():
    cfg = _cfg(
        sources=[
            {"name": "S1", "type": "rss", "url": "http://x", "max_items": 1},
        ],
        filters={"lookback_hours": 24, "max_items_per_source": 15, "max_items_total": 40},
    )
    items = [_item("a", "http://a", 1), _item("b", "http://b", 2)]
    out = select_items(items, cfg, NoopStateStore())
    assert len(out) == 1


def test_state_store_skips_seen(tmp_path):
    cfg = _cfg()
    store = JsonStateStore(tmp_path / "seen.json", retention_days=14)
    item = _item("a", "http://a", 1)
    store.mark(item.content_hash)
    out = select_items([item], cfg, store)
    assert out == []


def test_json_state_roundtrip(tmp_path):
    path = tmp_path / "seen.json"
    s1 = JsonStateStore(path, retention_days=14)
    s1.mark("hash123")
    s1.commit()
    s2 = JsonStateStore(path, retention_days=14)
    assert s2.seen("hash123")
