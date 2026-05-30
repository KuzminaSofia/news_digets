"""End-to-end pipeline test with fake source / LLM / delivery (no network)."""

from datetime import datetime, timezone

from digest_engine.config import Config
from digest_engine.delivery.base import DeliveryChannel, register_channel
from digest_engine.llm.base import LLMProvider, register_provider
from digest_engine.models import RawItem
from digest_engine.pipeline import run
from digest_engine.sources.base import Source, register_source

DELIVERED: list = []


@register_source("fake")
class FakeSource(Source):
    def fetch(self):
        now = datetime.now(timezone.utc)
        return [
            RawItem("Fake", "First item", "https://x.com/1", "<p>Body one</p>", now),
            RawItem("Fake", "Second item", "https://x.com/2", "Body two", now),
            RawItem("Fake", "Dupe of first", "https://x.com/1", "again", now),
        ]


@register_provider("fake-llm")
class FakeProvider(LLMProvider):
    def chat(self, system: str, user: str) -> str:
        # Return strict JSON for whatever indices appear; assume up to 2 here.
        return (
            '[{"index": 0, "headline": "HL0", "summary": "S0", "topics": ["x"]},'
            ' {"index": 1, "headline": "HL1", "summary": "S1", "topics": []}]'
        )


@register_channel("fake-delivery")
class FakeChannel(DeliveryChannel):
    def deliver(self, digest):
        DELIVERED.append(digest)


def _config():
    return Config.model_validate(
        {
            "name": "Pipe Test",
            "language": "en",
            "sources": [{"name": "Fake", "type": "fake", "url": "n/a"}],
            "llm": {"provider": "fake-llm", "api_key_env": "UNUSED"},
            "delivery": {"type": "fake-delivery"},
        }
    )


def test_pipeline_dry_run_builds_but_does_not_deliver():
    DELIVERED.clear()
    result = run(_config(), dry_run=True)
    # 3 raw -> dupe removed -> 2 entries.
    assert len(result.digest.entries) == 2
    assert result.delivered is False
    assert DELIVERED == []
    assert result.digest.entries[0].headline == "HL0"


def test_pipeline_real_run_delivers():
    DELIVERED.clear()
    result = run(_config(), dry_run=False)
    assert result.delivered is True
    assert len(DELIVERED) == 1
    assert len(DELIVERED[0].entries) == 2
