"""Source implementations. Importing this package registers all built-in types."""

from digest_engine.sources.base import Source, build_source, register_source
from digest_engine.sources.rss import RSSSource

__all__ = ["Source", "build_source", "register_source", "RSSSource"]
