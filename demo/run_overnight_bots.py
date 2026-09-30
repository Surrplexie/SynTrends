"""Run multiple overnight bots against one live testnet (same chain).

Each agent needs its own owner-portal API key. Stagger starts so polls do not
align on the same second.

Example::

    python scripts/ship_testnet.py --no-e2e --port 8099

    copy demo\\overnight_agents.example.json demo\\overnight_agents.local.json
    # edit keys/agent ids, then:
    python -m demo.run_overnight_bots --config demo/overnight_agents.local.json --hours 4
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

from demo.overnight_bot import DEFAULT_BASE_URL, DEFAULT_BUY_AMOUNT, DEFAULT_INTERVAL_S, DEFAULT_SELL_AFTER_BUYS, DEFAULT_SELL_FRACTION, DEFAULT_TICKER, _utc_now, build_bot


def _load_agents(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("config must be a non-empty JSON array of agent objects")
    agents: list[dict] = []
    for i, row in enumerate(data):
        if not isinstance(row, dict):
            raise ValueError(f"agent entry {i} must be an object")
        agent_id = str(row.get("agent_id", "")).strip()
        api_key = str(row.get("api_key", "")).strip()
        if not agent_id or not api_key:
            raise ValueError(f"agent entry {i} needs agent_id and api_key")
        agents.append(row)
    return agents


def _run_one(
    *,
    base_url: str,
    row: dict,
    hours: float,
    stagger_s: float,
    slot: int,
    defaults: dict,
) -> None:
    time.sleep(slot * stagger_s)
    agent_id = str(row["agent_id"])
    api_key = str(row["api_key"])
    bot, client = build_bot(
        base_url=base_url,
        api_key=api_key,
        agent_id=agent_id,
        ticker=str(row.get("ticker", defaults["ticker"])),
        buy_amount=float(row.get("buy_amount", defaults["buy_amount"])),
        interval_s=float(row.get("interval", defaults["interval"])),
        sell_after_buys=int(row.get("sell_after_buys", defaults["sell_after_buys"])),
        sell_fraction=float(row.get("sell_fraction", defaults["sell_fraction"])),
    )
    deadline = time.monotonic() + hours * 3600
    offset = slot * stagger_s
    print(
        f"[{_utc_now()}] worker {slot + 1} starting agent={agent_id} "
        f"stagger={offset:.0f}s interval~{bot.interval_s}s",
        flush=True,
    )
    try:
        bot.run_until(deadline)
    except KeyboardInterrupt:
        bot.log(f"interrupted — {bot.stats.summary()}")
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run multiple SynTrends overnight bots")
    parser.add_argument("--config", required=True, help="JSON file listing agents + api keys")
    parser.add_argument("--base-url", default=os.environ.get("SYNTRENDS_URL", DEFAULT_BASE_URL))
    parser.add_argument("--hours", type=float, default=float(os.environ.get("SYNTRENDS_HOURS", "4")))
    parser.add_argument(
        "--stagger",
        type=float,
        default=float(os.environ.get("SYNTRENDS_STAGGER", "20")),
        help="Seconds between starting each bot (default 20)",
    )
    parser.add_argument("--ticker", default=os.environ.get("SYNTRENDS_TICKER", DEFAULT_TICKER))
    parser.add_argument("--buy-amount", type=float, default=float(os.environ.get("SYNTRENDS_BUY_AMOUNT", DEFAULT_BUY_AMOUNT)))
    parser.add_argument("--interval", type=float, default=float(os.environ.get("SYNTRENDS_INTERVAL", DEFAULT_INTERVAL_S)))
    parser.add_argument(
        "--sell-after-buys",
        type=int,
        default=int(os.environ.get("SYNTRENDS_SELL_AFTER_BUYS", DEFAULT_SELL_AFTER_BUYS)),
    )
    parser.add_argument(
        "--sell-fraction",
        type=float,
        default=float(os.environ.get("SYNTRENDS_SELL_FRACTION", DEFAULT_SELL_FRACTION)),
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_file():
        print(f"Config not found: {config_path}", file=sys.stderr)
        sys.exit(2)
    if args.hours <= 0:
        print("--hours must be positive", file=sys.stderr)
        sys.exit(2)

    agents = _load_agents(config_path)
    defaults = {
        "ticker": args.ticker,
        "buy_amount": args.buy_amount,
        "interval": args.interval,
        "sell_after_buys": args.sell_after_buys,
        "sell_fraction": args.sell_fraction,
    }
    print(
        f"[{_utc_now()}] launching {len(agents)} bots — url={args.base_url} hours={args.hours} "
        f"stagger={args.stagger}s",
        flush=True,
    )

    threads: list[threading.Thread] = []
    for i, row in enumerate(agents):
        t = threading.Thread(
            target=_run_one,
            kwargs={
                "base_url": args.base_url,
                "row": row,
                "hours": args.hours,
                "stagger_s": args.stagger,
                "slot": i,
                "defaults": defaults,
            },
            name=f"overnight-{row.get('agent_id', i)}",
            daemon=False,
        )
        threads.append(t)
        t.start()

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print(f"[{_utc_now()}] stopping — waiting for workers...", flush=True)
        for t in threads:
            t.join(timeout=5.0)
    print(f"[{_utc_now()}] all workers done", flush=True)


if __name__ == "__main__":
    main()
