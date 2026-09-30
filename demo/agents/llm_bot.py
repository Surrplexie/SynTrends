"""Optional LLM-style agent: heuristic strategy with a clear LLM swap-in point.

Without an API key for OpenAI/Anthropic, this bot uses a simple keyword
sentiment heuristic on Seepnews bodies. Replace ``decide_action()`` with an
LLM call to upgrade to true model-driven strategy.

Standalone::

    python -m demo.run_api   # other terminal
    python -m demo.agents.llm_bot
"""

from __future__ import annotations

import os
import time

from chain.stp import ParsedSeepnews, ParsedTicker, STPRecord
from syntrends.client import DEFAULT_BASE_URL, SynTrendsClient
from syntrends.state import MarketView

POSITIVE = ("surge", "breakout", "momentum", "bull", "gain", "up")
NEGATIVE = ("dump", "crash", "bear", "loss", "down", "freeze")
DEFAULT_TICKER = "GEM"
BUY_AMOUNT = 75.0
COOLDOWN_S = 3.0


def decide_action(news_body: str, ticker: ParsedTicker | None) -> str | None:
    """Replace this function with an LLM prompt → action parser for production."""
    if ticker and ticker.freeze == "frozen":
        return None
    lower = news_body.lower()
    score = sum(w in lower for w in POSITIVE) - sum(w in lower for w in NEGATIVE)
    if score >= 1 and ticker:
        return "buy"
    if score <= -2 and ticker:
        return "sell"
    return None


class LLMBot:
    def __init__(self, name: str, client: SynTrendsClient, ticker: str = DEFAULT_TICKER):
        self.name = name
        self.client = client
        self.ticker = ticker
        self.view = MarketView()
        self._last_action_at = 0.0

    def log(self, msg: str) -> None:
        print(f"[{self.name}] {msg}")

    def bootstrap(self) -> None:
        self.view.apply_many(self.client.snapshot_records())
        self.log("bootstrap complete (heuristic mode — swap decide_action for LLM)")

    def on_records(self, records: list[STPRecord]) -> list[STPRecord]:
        self.view.apply_many(records)
        now = time.time()
        if now - self._last_action_at < COOLDOWN_S:
            return []

        ticker = self.view.tickers.get(self.ticker)
        news_body = ""
        for record in records:
            if isinstance(record, ParsedSeepnews):
                news_body += " " + record.extra.get("MSG", "")

        action = decide_action(news_body.strip(), ticker)
        if not action or not ticker:
            return []

        self._last_action_at = now
        if action == "buy":
            self.log(f"heuristic buy ${self.ticker} ({BUY_AMOUNT} fiat)")
            return self.client.buy(ticker=self.ticker, fiat_amount=BUY_AMOUNT)
        if action == "sell" and ticker.price > 0:
            self.log(f"heuristic sell ${self.ticker}")
            return self.client.sell(ticker=self.ticker, coin_amount=5.0)
        return []


def main() -> None:
    base = os.environ.get("SYNTRENDS_API_URL", DEFAULT_BASE_URL)
    key = os.environ.get("SYNTRENDS_AGENT_KEY")
    if not key:
        with __import__("httpx").Client(base_url=base, timeout=10.0) as c:
            key = c.get("/demo/keys").json()["agent_key"]
    client = SynTrendsClient(base_url=base, agent_key=key)
    bot = LLMBot("llm-heuristic", client)
    bot.bootstrap()
    for _ in range(30):
        records = bot.client.snapshot_records()
        bot.on_records(records)
        time.sleep(1.0)


if __name__ == "__main__":
    main()
