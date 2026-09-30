"""Seed simulated chain history and persist to SQLite or PostgreSQL.

    python -m demo.seed_history
    python -m demo.seed_history --output sqlite:///data/demo.db
    DATABASE_URL=postgresql://... python -m demo.seed_history
"""

from __future__ import annotations

import argparse
import os

from api.persistence import Persistence
from api.service import SynTrendsAPIService
from chain.clock import ManualClock


def seed_history(*, database_url: str | None = None, rounds: int = 40) -> dict:
    clock = ManualClock(start=1_700_000_000.0)
    persistence = Persistence(database_url) if database_url else None
    svc = SynTrendsAPIService(clock=clock, persistence=persistence)
    svc.seed_demo()

    founder = "agent-founder"
    trader_a = "agent-trader-a"
    trader_b = "agent-trader-b"
    gem = next(c for c in svc.demo.coins.values() if c.ticker == "GEM")

    for i in range(rounds):
        agent = trader_a if i % 2 == 0 else trader_b
        amount = 50.0 + (i % 5) * 25.0
        try:
            svc.demo.buy(agent, gem.coin_id, amount)
        except Exception:
            pass
        svc.demo.tick(gem.coin_id)
        if i % 5 == 0:
            svc.demo.mine_block()

    svc.demo.mine_block()
    svc.persist()
    return {
        "blocks": len(svc.demo.chain.chain),
        "agents": len(svc.demo.agents),
        "database_url": database_url,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed SynTrends demo chain history")
    parser.add_argument(
        "--output",
        default=os.environ.get("DATABASE_URL", "sqlite:///data/demo.db"),
        help="sqlite:///path or postgresql://… (default: sqlite:///data/demo.db)",
    )
    parser.add_argument("--rounds", type=int, default=40)
    args = parser.parse_args()

    if args.output.startswith("sqlite:///"):
        path = args.output.removeprefix("sqlite:///")
        if path.startswith("/"):
            db_path = path
        else:
            db_path = path
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    stats = seed_history(database_url=args.output, rounds=args.rounds)
    print(f"Seeded {stats['blocks']} blocks, {stats['agents']} agents → {stats['database_url']}")


if __name__ == "__main__":
    main()
