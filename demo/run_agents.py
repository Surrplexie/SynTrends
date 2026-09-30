"""Phase C demo: reference agents (trader / reader / hybrid) trading and
reading via the SynTrends SDK against the Phase B HTTP API — fully
in-process and deterministic (no real network, no threads, no ports).

    python -m demo.run_agents

For a genuinely live, multi-process demo instead: start the server in one
terminal, then run each bot standalone in its own terminal against it::

    python -m demo.run_api
    python -m demo.agents.trader_bot
    python -m demo.agents.reader_bot
    python -m demo.agents.digest_bot
    python -m demo.agents.hybrid_bot
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app, get_service
from chain.stp import STPRecord
from demo.agents.hybrid_bot import HybridBot
from demo.agents.reader_bot import ReaderBot
from demo.agents.trader_bot import TraderBot
from demo.agents._bootstrap import accept_platform_terms
from syntrends.client import SynTrendsClient
from syntrends.errors import RateLimitedError

MAX_ROUNDS = 60
POST_FREEZE_ROUNDS = 20  # keep background agent under 60 writes/min with step 3 buys


def line(title: str = "") -> None:
    print("\n" + "=" * 78)
    if title:
        print(title)
        print("=" * 78)


def broadcast_cascade(records: list[STPRecord], bots: list, max_rounds: int = 5) -> None:
    """Feed records to every bot; any records a bot's reaction produces get
    fed to everyone again, so second-order effects (e.g. a bot's own
    post-unfreeze buy) are observed too. Bots dedupe internally, so
    re-delivery of already-seen state is always safe.
    """
    pending = list(records)
    rounds = 0
    while pending and rounds < max_rounds:
        rounds += 1
        next_pending: list[STPRecord] = []
        for bot in bots:
            next_pending.extend(bot.on_records(pending))
        pending = next_pending


def main() -> None:
    with TestClient(app) as tc:
        svc = get_service()

        line("0. In-process API ready (seeded market: $GEM, agent-founder/trader-a/trader-b)")
        print(f"  seeded agent key (agent-trader-a): {svc.demo_agent_key[:24]}...")
        print(f"  seeded 3rdPS API key:             {svc.demo_thirdps_key[:24]}...")

        line("1. Bootstrap reference agents via SDK (POST /keys/agent) + 3rdPS demo (POST /keys/thirdps)")
        trader_client = SynTrendsClient.register_agent(agent_id="agent-trader-bot", client=tc)
        reader_client = SynTrendsClient.register_agent(agent_id="agent-reader-bot", client=tc)
        hybrid_client = SynTrendsClient.register_agent(agent_id="agent-hybrid-bot", client=tc)
        thirdps_client = SynTrendsClient.issue_thirdps_client(client=tc, label="demo chart vendor")
        print("  registered: agent-trader-bot, agent-reader-bot, agent-hybrid-bot")
        print(f"  issued 3rdPS API key: {thirdps_client.api_key[:24]}...")

        for client in (trader_client, reader_client, hybrid_client):
            accept_platform_terms(client)

        trader_client.deposit("agent-trader-bot", 20_000)
        hybrid_client.deposit("agent-hybrid-bot", 20_000)

        trader = TraderBot("agent-trader-bot", trader_client)
        reader = ReaderBot("agent-reader-bot", reader_client)
        hybrid = HybridBot("agent-hybrid-bot", hybrid_client)
        bots = [trader, reader, hybrid]

        line("2. Bots bootstrap from GET /snapshot")
        for bot in bots:
            bot.bootstrap()

        line("3. Ambient market activity: the seeded agent-trader-a keeps buying $GEM")
        background = SynTrendsClient(client=tc, api_key=svc.demo_agent_key)
        rounds = 0
        while rounds < MAX_ROUNDS:
            rounds += 1
            records = background.buy(ticker="GEM", fiat_amount=200.0)
            broadcast_cascade(records, bots)

            gem = trader.view.tickers.get("GEM")
            if gem and gem.freeze == "frozen":
                print(f"  -- $GEM froze after {rounds} ambient buys, ceiling ~{gem.ceil:.6f} --")
                break
        else:
            print("  -- $GEM never froze in the round budget; continuing anyway --")

        line("4. Cooldown elapses -> freeze lifts (advance the demo clock)")
        svc.clock.advance(11.0)
        records = background.tick(ticker="GEM")
        broadcast_cascade(records, bots)
        print(f"  freeze state now: {trader.view.tickers['GEM'].freeze}")

        line("5. More ambient buying to fill the hybrid bot's post-freeze order")
        for i in range(POST_FREEZE_ROUNDS):
            try:
                records = background.buy(ticker="GEM", fiat_amount=300.0)
            except RateLimitedError:
                print(f"  -- background agent hit write rate limit after {i} post-freeze rounds --")
                break
            broadcast_cascade(records, bots)
            try:
                records = background.tick(ticker="GEM")
            except RateLimitedError:
                print(f"  -- background agent hit write rate limit on tick after {i} post-freeze rounds --")
                break
            broadcast_cascade(records, bots)
            filled = [p for p in hybrid.view.pfos.values() if p.status != "pending"]
            if filled:
                print(f"  -- post-freeze order resolved: {filled[-1].status} after {i + 1} rounds --")
                break
        else:
            print("  -- post-freeze order still pending after the round budget --")

        line("6. Reader bot digest + Seepnews stats")
        print(f"  reader ingested {len(reader.view.seepnews)} Seepnews posts")
        print(f"  category counts: {dict(reader.category_counts)}")

        line("7. Final leaderboard (fetched with a 3rdPS API read-only key)")
        view = thirdps_client.snapshot_view()
        for rank, ticker_sym, value in view.leaderboard:
            print(f"  {rank}. ${ticker_sym} mcap=${value:,.2f}")
        thirdps_snapshot = thirdps_client.snapshot()
        print(f"  3rdPS snapshot excludes wallets: {'ST/W' not in thirdps_snapshot}")

        line("8. Bot logs (tail)")
        for bot in bots:
            print(f"-- {bot.name} --")
            for entry in bot.log_lines[-6:]:
                print(f"  {entry}")

        for c in (trader_client, reader_client, hybrid_client, thirdps_client, background):
            c.close()

    line("Phase C demo complete")


if __name__ == "__main__":
    main()
