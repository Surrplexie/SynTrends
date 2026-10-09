"""In-process demo miner — local only, not a public Fly node.

Hosted testnet mines inside the API on trades/ticks. Strangers cannot attach
miners to testnet.syntrends.com until a node protocol ships.

    python -m demo.run_miner --blocks 3
"""

from __future__ import annotations

import argparse
import time

from chain.engine import SynTrendsDemo


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine local demo blocks (not public testnet).")
    parser.add_argument("--blocks", type=int, default=3)
    parser.add_argument("--interval", type=float, default=0.2)
    args = parser.parse_args()
    demo = SynTrendsDemo()
    demo.register_agent("miner-local")
    for n in range(max(1, args.blocks)):
        demo.chain.add_transaction("miner_heartbeat", {"n": n, "agent": "miner-local"})
        block = demo.mine_block()
        if block is None:
            print("no block")
            continue
        print(f"height={block.index} hash={block.hash[:20]} txs={len(block.transactions)}")
        time.sleep(max(0.0, args.interval))
    print("local miner done (this did not talk to Fly)")


if __name__ == "__main__":
    main()
