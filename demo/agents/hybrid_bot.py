"""Reference hybrid bot: reads Seepnews for freeze signals AND trades — the
spec's "hybrid agent" archetype (does both trading and reading, unlike the
pure trader or pure reader).

    python -m demo.agents.hybrid_bot
"""

from __future__ import annotations

import os

from chain.stp import ParsedError, ParsedFreezeEvent, ParsedSeepnews, STPRecord
from demo.agents._bootstrap import accept_platform_terms
from syntrends.client import DEFAULT_BASE_URL, SynTrendsClient
from syntrends.state import MarketView

DEFAULT_TICKER = "GEM"
PFO_BUY_AMOUNT = 300.0
PFO_TARGET_MULTIPLIER = 1.03  # bet price rises 3% above the freeze ceiling once it lifts
UNFREEZE_NIBBLE_FIAT = 100.0


class HybridBot:
    """Places a Post-Freeze Order the moment a freeze is detected, buys a
    small amount the moment it lifts, and otherwise just observes.
    """

    def __init__(self, name: str, client: SynTrendsClient, ticker: str = DEFAULT_TICKER):
        self.name = name
        self.client = client
        self.ticker = ticker
        self.view = MarketView()
        self._pfo_placed_for_ceiling: set[float] = set()
        self._last_freeze_event: str | None = None
        self._seen_post_ids: set[str] = set()
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
            self._last_freeze_event = "freeze_active" if t.freeze == "frozen" else t.freeze
        self.log(f"bootstrap: watching ${self.ticker}")

    def on_records(self, records: list[STPRecord]) -> list[STPRecord]:
        self.view.apply_many(records)
        produced: list[STPRecord] = []
        for record in records:
            if isinstance(record, ParsedSeepnews):
                if record.post_id in self._seen_post_ids:
                    continue
                self._seen_post_ids.add(record.post_id)
                if record.category == "Freezes" and record.ticker == self.ticker:
                    ceil = record.extra.get("CEIL")
                    self.log(f"saw freeze news for ${self.ticker} at ${ceil}")
            elif isinstance(record, ParsedFreezeEvent) and record.ticker == self.ticker:
                produced.extend(self._on_freeze_transition(record))
        return produced

    def _on_freeze_transition(self, record: ParsedFreezeEvent) -> list[STPRecord]:
        prev = self._last_freeze_event
        self._last_freeze_event = record.event
        if record.event == "freeze_active":
            return self._maybe_place_pfo(record.ceil)
        if record.event == "growing" and prev == "freeze_active":
            return self._on_unfreeze()
        return []

    def _maybe_place_pfo(self, ceiling: float | None) -> list[STPRecord]:
        if ceiling is None or ceiling in self._pfo_placed_for_ceiling:
            return []
        self._pfo_placed_for_ceiling.add(ceiling)
        target = ceiling * PFO_TARGET_MULTIPLIER
        try:
            result = self.client.place_pfo(
                ticker=self.ticker, side="buy", target_price=target, amount=PFO_BUY_AMOUNT,
            )
        except Exception as exc:
            self.log(f"could not place post-freeze order: {exc}")
            return []
        errors = [r for r in result if isinstance(r, ParsedError)]
        if errors:
            self.log(f"post-freeze order rejected: {errors[0].msg}")
        else:
            self.log(f"placed post-freeze buy order: {PFO_BUY_AMOUNT} @ target ${target:.6f}")
        return result

    def _on_unfreeze(self) -> list[STPRecord]:
        self.log(f"${self.ticker} unfroze; nibbling back in")
        try:
            result = self.client.buy(ticker=self.ticker, fiat_amount=UNFREEZE_NIBBLE_FIAT)
        except Exception as exc:
            self.log(f"post-unfreeze buy failed: {exc}")
            return []
        errors = [r for r in result if isinstance(r, ParsedError)]
        if errors:
            self.log(f"post-unfreeze buy rejected: {errors[0].msg}")
        else:
            self.log("post-unfreeze buy executed")
        return result

    def run_forever(self, tail: int = 0) -> None:
        self.bootstrap()
        for record in self.client.stream_all(tail=tail, live=True):
            self.on_records([record])


def main() -> None:
    base_url = os.environ.get("SYNTRENDS_URL", DEFAULT_BASE_URL)
    agent_id = os.environ.get("SYNTRENDS_AGENT_ID", "agent-hybrid-bot")
    ticker = os.environ.get("SYNTRENDS_TICKER", DEFAULT_TICKER)

    client = SynTrendsClient.register_agent(base_url, agent_id, label="reference hybrid bot")
    client.deposit(agent_id, 20_000.0)
    bot = HybridBot(agent_id, client, ticker=ticker)
    print(f"[{agent_id}] connected to {base_url}, hybrid strategy on ${bot.ticker}")
    try:
        bot.run_forever()
    except KeyboardInterrupt:
        print(f"[{agent_id}] stopped")
    finally:
        client.close()


if __name__ == "__main__":
    main()
