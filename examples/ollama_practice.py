"""Local Ollama + SynTrends testnet practice loop.

Ollama decides; this process places orders. syntrends.com is only KYC/keys —
the bot talks to https://testnet.syntrends.com.

  ollama list
  ollama pull llama3.1
  $env:SYNTRENDS_API_KEY = "st_agent_..."   # portal key, not pasted in chat
  $env:SYNTRENDS_URL = "https://testnet.syntrends.com"
  $env:OLLAMA_MODEL = "llama3.1"
  $env:DRY_RUN = "1"
  python examples/ollama_practice.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

import httpx

from syntrends import SynTrendsClient

TICKER = os.environ.get("SYNTRENDS_TICKER", "GEM")
BASE = os.environ.get("SYNTRENDS_URL", "https://testnet.syntrends.com").rstrip("/")
KEY = os.environ.get("SYNTRENDS_API_KEY", "").strip()
OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")
DRY = os.environ.get("DRY_RUN", "1").strip() not in ("0", "false", "no")
LOOPS = int(os.environ.get("PRACTICE_LOOPS", "8"))
SLEEP_S = float(os.environ.get("PRACTICE_SLEEP", "12"))
BUY_FIAT = float(os.environ.get("BUY_FIAT", "15"))
SELL_COINS = float(os.environ.get("SELL_COINS", "5"))

SYSTEM = """You are a SynTrends testnet trading agent. Simulated fiat only.
Reply with JSON only: {"action":"buy"|"sell"|"hold","reason":"short"}
Skip buy if freeze is frozen or price is at/above ceil.
Prefer hold. Do not invent tickers. One action per turn."""


def ollama_decide(prompt: str) -> dict:
    r = httpx.post(
        f"{OLLAMA}/api/chat",
        json={
            "model": MODEL,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=120.0,
    )
    r.raise_for_status()
    raw = r.json()["message"]["content"]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        return json.loads(m.group(0)) if m else {"action": "hold", "reason": "unparsed"}


def main() -> None:
    if not KEY:
        print("Set SYNTRENDS_API_KEY", file=sys.stderr)
        sys.exit(2)

    tags = httpx.get(f"{OLLAMA}/api/tags", timeout=5.0)
    tags.raise_for_status()
    names = [m.get("name", "") for m in tags.json().get("models", [])]
    if not any(MODEL in n or n.startswith(MODEL) for n in names):
        print(f"Ollama has no model matching {MODEL!r}. Run: ollama pull {MODEL}", file=sys.stderr)
        print("Installed:", names or "(none)")
        sys.exit(2)

    print(f"venue={BASE}  model={MODEL}  dry_run={DRY}  loops={LOOPS}")
    client = SynTrendsClient(base_url=BASE, api_key=KEY, timeout=30.0)
    try:
        client.agree_syntrends()
        client.agree_seepnews()
        faucet = httpx.post(
            f"{BASE}/testnet/faucet",
            headers={"Authorization": f"Bearer {KEY}"},
            timeout=30.0,
        )
        print(f"faucet HTTP {faucet.status_code}")

        for i in range(LOOPS):
            view = client.snapshot_view()
            t = view.tickers.get(TICKER)
            if t is None:
                print(f"no {TICKER} on snapshot")
                sys.exit(1)
            prompt = (
                f"ticker={TICKER} price={t.price:.6f} freeze={t.freeze} "
                f"ceil={t.ceil} next_ceil={t.next_ceil} fee_pct={t.fee_pct}\n"
                f"wallets_fiat={view.wallets_fiat}\n"
                f"recent_trades={len(view.trades)} seepnews={len(view.seepnews)}\n"
                f"Decide now."
            )
            decision = ollama_decide(prompt)
            action = str(decision.get("action", "hold")).lower().strip()
            reason = decision.get("reason", "")
            print(f"[{i+1}/{LOOPS}] {action}  freeze={t.freeze} price={t.price:.4f}  {reason}")

            if DRY or action == "hold":
                time.sleep(SLEEP_S)
                continue
            frozen = t.freeze in ("frozen", "freeze_active")
            if action == "buy":
                if frozen:
                    print("  skip buy (frozen)")
                else:
                    recs = client.buy(ticker=TICKER, fiat_amount=BUY_FIAT)
                    print(f"  buy {BUY_FIAT} -> {len(recs)} STP lines")
            elif action == "sell":
                recs = client.sell(ticker=TICKER, coin_amount=SELL_COINS)
                print(f"  sell {SELL_COINS} -> {len(recs)} STP lines")
            time.sleep(SLEEP_S)
    finally:
        client.close()


if __name__ == "__main__":
    main()
