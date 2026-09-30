"""Phase C reference agent tests: bot decision logic against the in-process API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app, get_service
from demo.agents.hybrid_bot import HybridBot
from demo.agents.reader_bot import ReaderBot
from demo.agents.trader_bot import TraderBot
from syntrends.client import SynTrendsClient


@pytest.fixture
def tc():
    with TestClient(app) as c:
        yield c


def test_trader_bot_buys_on_momentum(tc: TestClient):
    client = SynTrendsClient.register_agent(agent_id="agent-test-trader", client=tc)
    client.agree_syntrends()
    client.deposit("agent-test-trader", 5_000.0)
    bot = TraderBot("agent-test-trader", client, ticker="GEM", buy_amount=50.0)
    bot.bootstrap()

    background = SynTrendsClient(client=tc, api_key=get_service().demo_agent_key)
    records = background.buy(ticker="GEM", fiat_amount=200.0)  # big pump -> should trigger momentum buy
    bot.on_records(records)

    assert any("bought" in entry for entry in bot.log_lines)


def test_trader_bot_holds_while_frozen(tc: TestClient):
    from chain.stp import ParsedTicker

    client = SynTrendsClient.register_agent(agent_id="agent-test-trader-frozen", client=tc)
    bot = TraderBot("agent-test-trader-frozen", client, ticker="GEM")
    bot.bootstrap()
    bot._last_seen_price = 1.0

    frozen_record = ParsedTicker(
        ticker="GEM", coin_id="x", price=1.5, mcap=100.0, pool_fiat=1.0, pool_coin=1.0,
        freeze="frozen", ceil=1.5, next_ceil=2.0, fee_pct=0.01, ts=0.0,
    )
    produced = bot.on_records([frozen_record])
    assert produced == []


def test_reader_bot_ingests_and_digests(tc: TestClient):
    client = SynTrendsClient.register_agent(agent_id="agent-test-reader", client=tc)
    bot = ReaderBot("agent-test-reader", client, digest_ticker="GEM")
    bot.bootstrap()

    poster = SynTrendsClient(client=tc, api_key=get_service().demo_agent_key)
    produced = []
    for i in range(5):
        records = poster.post_seepnews(
            "Trade", f"note number {i}", mentions=["GEM"], hashtags=["trending", "syntrends", "seepnews"]
        )
        produced.extend(bot.on_records(records))

    assert bot.category_counts["Trade"] >= 5
    assert produced, "reader should have posted a digest after 5 posts"


def test_reader_bot_ignores_duplicate_post_ids(tc: TestClient):
    client = SynTrendsClient.register_agent(agent_id="agent-test-reader-dup", client=tc)
    bot = ReaderBot("agent-test-reader-dup", client, digest_ticker="GEM")
    bot.bootstrap()

    poster = SynTrendsClient(client=tc, api_key=get_service().demo_agent_key)
    records = poster.post_seepnews(
        "Trade", "dup test", mentions=["GEM"], hashtags=["trending", "syntrends", "seepnews"]
    )
    bot.on_records(records)
    count_after_first = bot.category_counts["Trade"]
    bot.on_records(records)  # re-deliver the same records (as a live stream replay would)
    assert bot.category_counts["Trade"] == count_after_first


def test_hybrid_bot_places_pfo_on_freeze_and_buys_on_unfreeze(tc: TestClient):
    svc = get_service()
    client = SynTrendsClient.register_agent(agent_id="agent-test-hybrid", client=tc)
    client.agree_syntrends()
    client.deposit("agent-test-hybrid", 20_000.0)
    bot = HybridBot("agent-test-hybrid", client, ticker="GEM")
    bot.bootstrap()

    background = SynTrendsClient(client=tc, api_key=svc.demo_agent_key)

    froze = False
    for _ in range(30):
        records = background.buy(ticker="GEM", fiat_amount=200.0)
        bot.on_records(records)
        view = client.snapshot_view()
        if view.is_frozen("GEM"):
            froze = True
            break
    assert froze, "GEM should have frozen from repeated ambient buying"
    assert any("placed post-freeze buy order" in entry for entry in bot.log_lines)

    svc.clock.advance(11.0)
    records = background.tick(ticker="GEM")
    bot.on_records(records)
    assert any("unfroze" in entry for entry in bot.log_lines)
    assert any("post-unfreeze buy executed" in entry for entry in bot.log_lines)
