"""Command-line entry point.

Usage:
    run-digest --config configs/torchlab-ai.yml
    run-digest --config configs/torchlab-ai.yml --dry-run
"""

from __future__ import annotations

import argparse
import sys

from digest_engine.config import load_config
from digest_engine.logging_config import setup_logging
from digest_engine.pipeline import run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run-digest", description="Run a news digest.")
    parser.add_argument("--config", "-c", required=True, help="Path to a YAML config file.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and print the digest but do not deliver or persist state.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.log_level)

    config = load_config(args.config)
    result = run(config, dry_run=args.dry_run)

    if args.dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN — preview (not delivered):\n")
        print(result.markdown or "(empty digest)")
        print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
