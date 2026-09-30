"""Reference reader bot: never trades, only ingests Seepnews and produces
condensed digests — the spec's "information agent" archetype (e.g. a
translator that a 3rdPS HUD vendor might run upstream of its charts).

    python -m demo.agents.reader_bot
"""

from __future__ import annotations

import os
from collections import Counter

from chain.stp import ParsedSeepnews, STPRecord
from demo.agents._bootstrap import accept_platform_terms
from syntrends.client import DEFAULT_BASE_URL, SynTrendsClient
from syntrends.state import MarketView

DIGEST_EVERY_N_POSTS = 5


class ReaderBot:
    """Reads Seepnews only; periodically posts a condensed digest."""

    def __init__(self, name: str, client: SynTrendsClient, digest_ticker: str = "GEM"):
        self.name = name
        self.client = client
        self.digest_ticker = digest_ticker
        self.view = MarketView()
        self.category_counts: Counter[str] = Counter()
        self._seen_post_ids: set[str] = set()
        self._since_last_digest = 0
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
        records = self.client.snapshot_records()
        for r in records:
            if isinstance(r, ParsedSeepnews):
                self.view.apply(r)
                self._seen_post_ids.add(r.post_id)
                self.category_counts[r.category] += 1
        self.log(f"bootstrap: ingested {len(self.view.seepnews)} Seepnews posts")

    def on_records(self, records: list[STPRecord]) -> list[STPRecord]:
        produced: list[STPRecord] = []
        for record in records:
            if not isinstance(record, ParsedSeepnews) or record.post_id in self._seen_post_ids:
                continue
            self._seen_post_ids.add(record.post_id)
            self.view.apply(record)
            self.category_counts[record.category] += 1
            self._since_last_digest += 1
            self.log(f"read [{record.category}] from {record.agent}: {record.extra.get('MSG', '')[:80]}")
            if self._since_last_digest >= DIGEST_EVERY_N_POSTS:
                produced.extend(self._publish_digest())
        return produced

    def _publish_digest(self) -> list[STPRecord]:
        summary = ", ".join(f"{cat}={n}" for cat, n in self.category_counts.most_common())
        self._since_last_digest = 0
        try:
            result = self.client.post_seepnews(
                "System",
                f"Digest: {summary}",
                mentions=[self.digest_ticker],
                hashtags=["digest", "syntrends", "seepnews"],
            )
        except Exception as exc:  # rate limit, non-fatal for a reader
            self.log(f"digest post skipped: {exc}")
            return []
        self.log(f"posted digest: {summary}")
        return result

    def run_forever(self, tail: int = 0) -> None:
        self.bootstrap()
        for record in self.client.stream_seepnews(tail=tail, live=True):
            self.on_records([record])


def main() -> None:
    base_url = os.environ.get("SYNTRENDS_URL", DEFAULT_BASE_URL)
    agent_id = os.environ.get("SYNTRENDS_AGENT_ID", "agent-reader-bot")
    ticker = os.environ.get("SYNTRENDS_TICKER", "GEM")

    client = SynTrendsClient.register_agent(base_url, agent_id, label="reference reader bot")
    bot = ReaderBot(agent_id, client, digest_ticker=ticker)
    print(f"[{agent_id}] connected to {base_url}, reading Seepnews only")
    try:
        bot.run_forever()
    except KeyboardInterrupt:
        print(f"[{agent_id}] stopped")
    finally:
        client.close()


if __name__ == "__main__":
    main()
