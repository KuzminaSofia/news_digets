#!/usr/bin/env python
"""Thin wrapper so the digest can be run as a script:

    python scripts/run_digest.py --config configs/torchlab-ai.yml [--dry-run]

(The same logic is exposed as the ``run-digest`` console command via pyproject.)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running without installation: add repo root to import path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from digest_engine.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
