"""Seed the public testnet genesis + simulated trade history.

    SYNTRENDS_ENV=testnet python -m demo.seed_testnet
    DATABASE_URL=postgresql://... SYNTRENDS_ENV=testnet python -m demo.seed_testnet
"""

from __future__ import annotations

import argparse
import os

from dataclasses import replace

from api.config import Settings
from api.persistence import Persistence
from api.service import SynTrendsAPIService
from chain.clock import ManualClock


def seed_testnet(*, database_url: str | None = None) -> dict:
    settings = Settings.from_env()
    if settings.env != "testnet":
        settings = replace(settings, env="testnet", database_url=database_url or settings.database_url)
    clock = ManualClock(start=1_700_000_000.0)
    persistence = Persistence(database_url) if database_url else None
    svc = SynTrendsAPIService(clock=clock, persistence=persistence, settings=settings, require_owner_kyc=True)
    stats = svc.seed_testnet()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed SynTrends public testnet")
    parser.add_argument(
        "--output",
        default=os.environ.get("DATABASE_URL", "sqlite:///data/testnet.db"),
        help="sqlite:///path or postgresql://…",
    )
    args = parser.parse_args()

    if args.output.startswith("sqlite:///"):
        path = args.output.removeprefix("sqlite:///")
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    os.environ.setdefault("SYNTRENDS_ENV", "testnet")
    stats = seed_testnet(database_url=args.output)
    print(f"Testnet seeded: {stats.get('blocks', '?')} blocks on {stats.get('network', 'testnet')} -> {args.output}")


if __name__ == "__main__":
    main()
