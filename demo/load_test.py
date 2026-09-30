"""Load test: concurrent agent buys against a running API.

Start the open API first::

    python -m demo.run_api

Then::

    python -m demo.load_test --agents 10 --tx 100

Targets ~1k tx/hour equivalent burst (completes in seconds against local API).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import time

import httpx


def fetch_keys(base_url: str) -> tuple[str, str]:
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        resp = client.get("/demo/keys")
        resp.raise_for_status()
        data = resp.json()
        return data["agent_key"], data.get("thirdps_key") or data.get("license_key", "")


def issue_agent_key(base_url: str, agent_id: str) -> str:
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        resp = client.post(
            "/keys/agent",
            json={"agent_id": agent_id, "label": "load test"},
        )
        resp.raise_for_status()
        return resp.json()["api_key"]


def run_buy(base_url: str, agent_key: str, amount: float) -> bool:
    headers = {"Authorization": f"Bearer {agent_key}"}
    try:
        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            resp = client.post(
                "/trade/buy",
                json={"ticker": "GEM", "fiat_amount": amount},
                headers=headers,
            )
            return resp.status_code == 200
    except httpx.HTTPError:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="SynTrends API load test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--agents", type=int, default=10)
    parser.add_argument("--tx", type=int, default=100, help="Total buy attempts")
    parser.add_argument("--amount", type=float, default=25.0)
    args = parser.parse_args()

    template_key, _ = fetch_keys(args.base_url)
    keys: list[str] = [template_key]
    for i in range(1, args.agents):
        keys.append(issue_agent_key(args.base_url, f"agent-load-{i}"))

    start = time.perf_counter()
    ok = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(args.agents, 20)) as pool:
        futures = [
            pool.submit(run_buy, args.base_url, keys[i % len(keys)], args.amount)
            for i in range(args.tx)
        ]
        for fut in concurrent.futures.as_completed(futures):
            if fut.result():
                ok += 1

    elapsed = time.perf_counter() - start
    rate = ok / elapsed * 3600 if elapsed > 0 else 0
    print(f"Completed {ok}/{args.tx} buys in {elapsed:.2f}s (~{rate:.0f} tx/hour equivalent)")


if __name__ == "__main__":
    main()
