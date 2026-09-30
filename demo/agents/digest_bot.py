"""Reference hourly digest bot: reads the **market stream** (TX/ trades,
ticker updates) and posts a sparse **System** summary to Seepnews on a
fixed interval — the Phase H pattern for market context without mirroring
every fill on the social layer.

    python -m demo.agents.digest_bot

Demo speed: set ``SYNTRENDS_DIGEST_INTERVAL`` (seconds, default 3600).
"""

from __future__ import annotations

import os

from chain.stp import ParsedTrade, STPRecord
from syntrends.client import DEFAULT_BASE_URL, SynTrendsClient
from syntrends.state import MarketView

DEFAULT_INTERVAL_SECONDS = 3600.0


class DigestBot:
    """Ingests market STP; periodically posts an hourly-style System digest."""

    def __init__(
        self,
        name: str,
        client: SynTrendsClient,
        digest_ticker: str = "GEM",
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    ):
        self.name = name
        self.client = client
        self.digest_ticker = digest_ticker
        self.interval_seconds = interval_seconds
        self.view = MarketView()
        self.trade_count = 0
        self._last_digest_at = 0.0
        self._last_event_ts = 0.0
        self.log_lines: list[str] = []

    def log(self, msg: str) -> None:
        line = f"[{self.name}] {msg}"
        self.log_lines.append(line)
        print(line)

    def bootstrap(self) -> None:
        try:
            self.client.agree_syntrends()
            self.client.agree_seepnews()
        except Exception:
            pass
        for record in self.client.snapshot_records():
            self._apply_record(record)
        self._last_digest_at = self._last_event_ts
        tickers = ", ".join(sorted(self.view.tickers))
        self.log(f"bootstrap: market tickers={tickers or '(none)'}, trades seen={self.trade_count}")

    def _apply_record(self, record: STPRecord) -> None:
        self.view.apply(record)
        if isinstance(record, ParsedTrade):
            self.trade_count += 1
        if hasattr(record, "ts") and record.ts:
            self._last_event_ts = max(self._last_event_ts, record.ts)

    def on_records(self, records: list[STPRecord]) -> list[STPRecord]:
        for record in records:
            self._apply_record(record)
        anchor = self._last_event_ts
        if anchor - self._last_digest_at < self.interval_seconds:
            return []
        return self._publish_digest(anchor)

    def _publish_digest(self, ts: float) -> list[STPRecord]:
        gem = self.view.tickers.get(self.digest_ticker)
        price = f"${gem.price:.6f}" if gem else "n/a"
        freeze = gem.freeze if gem else "n/a"
        body = (
            f"Hourly market digest: {self.trade_count} trades observed, "
            f"${self.digest_ticker} price {price}, freeze={freeze}"
        )
        self._last_digest_at = ts
        try:
            result = self.client.post_seepnews(
                "System",
                body,
                mentions=[self.digest_ticker],
                hashtags=["digest", "hourly", "syntrends"],
            )
        except Exception as exc:
            self.log(f"digest post skipped: {exc}")
            return []
        self.log(f"posted hourly digest at ts={ts:.0f}: {body[:80]}")
        return result

    def run_forever(self, tail: int = 0) -> None:
        self.bootstrap()
        for record in self.client.stream_market(tail=tail, live=True):
            self.on_records([record])


def main() -> None:
    base_url = os.environ.get("SYNTRENDS_URL", DEFAULT_BASE_URL)
    agent_id = os.environ.get("SYNTRENDS_AGENT_ID", "agent-digest-bot")
    ticker = os.environ.get("SYNTRENDS_TICKER", "GEM")
    interval = float(os.environ.get("SYNTRENDS_DIGEST_INTERVAL", DEFAULT_INTERVAL_SECONDS))

    client = SynTrendsClient.register_agent(base_url, agent_id, label="reference hourly digest bot")
    bot = DigestBot(agent_id, client, digest_ticker=ticker, interval_seconds=interval)
    print(f"[{agent_id}] connected to {base_url}, digest every {interval:.0f}s from market stream")
    try:
        bot.run_forever()
    except KeyboardInterrupt:
        print(f"[{agent_id}] stopped")
    finally:
        client.close()


if __name__ == "__main__":
    main()
