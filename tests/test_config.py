import pytest
from pydantic import ValidationError

from digest_engine.config import Config, _interpolate_env, load_config


def test_load_example_config():
    cfg = load_config("configs/example.yml")
    assert cfg.name == "Example Digest"
    assert cfg.llm.provider == "openrouter"
    # Disabled source is excluded from enabled_sources.
    assert all(s.enabled for s in cfg.enabled_sources)
    assert len(cfg.enabled_sources) < len(cfg.sources)


def test_load_torchlab_config():
    cfg = load_config("configs/torchlab-ai.yml")
    assert cfg.timezone == "Europe/Moscow"
    assert cfg.delivery.type == "telegram"
    assert cfg.filters.lookback_hours == 24


def test_env_interpolation(monkeypatch):
    monkeypatch.setenv("MY_MODEL", "anthropic/claude-haiku")
    result = _interpolate_env({"model": "${MY_MODEL}", "nested": ["${MY_MODEL}", "x"]})
    assert result == {"model": "anthropic/claude-haiku", "nested": ["anthropic/claude-haiku", "x"]}


def test_requires_at_least_one_source():
    with pytest.raises(ValidationError):
        Config.model_validate({"name": "t", "sources": []})
