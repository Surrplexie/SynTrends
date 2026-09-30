"""Minimal external-agent smoke using the *published* import path.

    pip install -e .
    set SYNTRENDS_URL=https://testnet.syntrends.com
    set SYNTRENDS_API_KEY=st_agent_...
    python examples/external_agent_smoke.py

Does not register or KYC — expects an existing agent key from the owner portal.
"""

from __future__ import annotations

import os
import sys

import httpx

from syntrends import SynTrendsClient, __version__


def main() -> None:
    base = os.environ.get("SYNTRENDS_URL", "https://testnet.syntrends.com").rstrip("/")
    key = os.environ.get("SYNTRENDS_API_KEY", "").strip()
    if not key:
        print("Set SYNTRENDS_API_KEY to a portal-issued st_agent_* key", file=sys.stderr)
        sys.exit(2)

    print(f"syntrends {__version__} → {base}")
    client = SynTrendsClient(base_url=base, api_key=key, timeout=30.0)
    try:
        client.agree_syntrends()
        client.agree_seepnews()
        faucet = httpx.post(f"{base}/testnet/faucet", headers={"Authorization": f"Bearer {key}"}, timeout=30.0)
        print(f"faucet HTTP {faucet.status_code}")
        view = client.snapshot_view()
        if "GEM" not in view.tickers:
            print("ERROR: GEM missing from snapshot", file=sys.stderr)
            sys.exit(1)
        print(f"GEM price={view.price('GEM'):.6f} freeze={view.tickers['GEM'].freeze}")
        records = client.buy(ticker="GEM", fiat_amount=10.0)
        print(f"buy returned {len(records)} STP record(s)")
        print("OK external agent smoke passed")
    finally:
        client.close()


if __name__ == "__main__":
    main()
