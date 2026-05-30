"""Config-driven news digest engine.

Pipeline: sources -> normalize -> filter/dedup -> summarize (LLM) -> render -> deliver.
Every stage is swappable; behaviour is driven entirely by a YAML config so the same
core can power digests for different people by only changing the config file.
"""

__version__ = "0.1.0"
