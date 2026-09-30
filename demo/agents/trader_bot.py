"""Reference momentum trader bot: buys into rising, non-frozen prices.

Standalone usage against a live server (run `python -m demo.run_api` in
another terminal first)::

    python -m demo.agents.trader_bot

``TraderBot`` is also reused directly by the in-process orchestrator
(``demo/run_agents.py``) via ``on_records()``.
"""

from __future__ import annotations

import os
import time

from chain.stp import ParsedError, ParsedTicker, STPRecord
from demo.agents._bootstrap import accept_platform_terms
from syntrends.client import DEFAULT_BASE_URL, SynTrendsClient
from syntrends.state import MarketView

DEFAULT_TICKER = "GEM"
BUY_AMOUNT = 150.0
MIN_GAIN_PCT = 0.02  # only buy if price rose >=2% since our last observation
ACTION_COOLDOWN_S = 2.0


class TraderBot:
    """Momentum strategy: reacts only to `ST/T` ticker lines."""

    def __init__(self, name: str, client: SynTrendsClient, ticker: str = DEFAULT_TICKER, buy_amount: float = BUY_AMOUNT):
        self.name = name
        self.client = client
        self.ticker = ticker
        self.buy_amount = buy_amount
        self.view = MarketView()
        self._last_seen_price: float | None = None
        self._last_action_at: float = 0.0
        self.log_lines: list[str] = []

    def log(self, msg: str) -> None:
        line = f"[{self.name}] {msg}"
        self.log_lines.append(line)
        print(line)

    def bootstrap(self) -> None:
        try:
            accept_platform_terms(self.client)
        except Exception:
            pass
        self.view.apply_many(self.client.snapshot_records())
        t = self.view.tickers.get(self.ticker)
        if t:
            self._last_seen_price = t.price
            self.log(f"bootstrap: ${self.ticker} @ {t.price:.6f} freeze={t.freeze}")

    def on_records(self, records: list[STPRecord]) -> list[STPRecord]:
        """Fold new records into local state; return any records produced by
        actions this bot decided to take in response (for cascading demos).
        """
        self.view.apply_many(records)
        produced: list[STPRecord] = []
        for record in records:
            if isinstance(record, ParsedTicker) and record.ticker == self.ticker:
                produced.extend(self._react_to_price(record))
        return produced

    def _react_to_price(self, record: ParsedTicker) -> list[STPRecord]:
        now = time.time()
        if self._last_seen_price is None:
            self._last_seen_price = record.price
            return []

        if record.freeze == "frozen":
            self._last_seen_price = record.price
            return []

        gain = (record.price - self._last_seen_price) / self._last_seen_price if self._last_seen_price else 0.0
        result: list[STPRecord] = []
        if gain >= MIN_GAIN_PCT and (now - self._last_action_at) >= ACTION_COOLDOWN_S:
            result = self.client.buy(ticker=self.ticker, fiat_amount=self.buy_amount)
            self._last_action_at = now
            errors = [r for r in result if isinstance(r, ParsedError)]
            if errors:
                self.log(f"buy rejected: {errors[0].msg}")
            else:
                self.log(
                    f"momentum +{gain:.2%} -> bought ${self.buy_amount:.2f} of ${self.ticker}, "
                    f"price now {record.price:.6f}"
                )

        self._last_seen_price = record.price
        return result

    def run_forever(self, tail: int = 0) -> None:
        """Live loop against a real running server (blocks)."""
        self.bootstrap()
        for record in self.client.stream_market(tail=tail, live=True):
            self.on_records([record])


def main() -> None:
    base_url = os.environ.get("SYNTRENDS_URL", DEFAULT_BASE_URL)
    agent_id = os.environ.get("SYNTRENDS_AGENT_ID", "agent-trader-bot")
    ticker = os.environ.get("SYNTRENDS_TICKER", DEFAULT_TICKER)

    client = SynTrendsClient.register_agent(base_url, agent_id, label="reference trader bot")
    client.deposit(agent_id, 20_000.0)
    bot = TraderBot(agent_id, client, ticker=ticker)
    print(f"[{agent_id}] connected to {base_url}, watching ${bot.ticker}")
    try:
        bot.run_forever()
    except KeyboardInterrupt:
        print(f"[{agent_id}] stopped")
    finally:
        client.close()


if __name__ == "__main__":
    main()
