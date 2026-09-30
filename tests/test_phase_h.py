"""Phase H: sparse Seepnews — no per-trade auto-posts, system events only,
duplicate body suppression, and reference digest bots."""

import pytest

from chain.clock import ManualClock
from chain.engine import SynTrendsDemo
from chain.freeze import FreezeState
from chain.seepnews import Seepnews, SeepnewsError
from chain.state_io import dump_demo, load_demo

TAGS = ["trending", "syntrends", "seepnews"]


def test_trades_do_not_auto_post_to_seepnews():
    clock = ManualClock(0.0)
    demo = SynTrendsDemo(clock=clock, seepnews_cooldown_seconds=0.0)
    demo.register_agent("founder")
    demo.register_agent("trader")
    demo.deposit_fiat("founder", 1000)
    demo.deposit_fiat("trader", 5000)
    coin = demo.launch_aicoin("GEM", "Gem", "founder", 10_000, 1000, 0.1)
    posts_after_launch = len(demo.seepnews.posts)

    for _ in range(10):
        demo.buy("trader", coin.coin_id, 50)

    assert len(demo.seepnews.posts) == posts_after_launch
    assert not any(p.category == "Trade" for p in demo.seepnews.posts)


def test_system_events_still_post_to_seepnews():
    clock = ManualClock(0.0)
    demo = SynTrendsDemo(cooldown_seconds=5.0, clock=clock, seepnews_cooldown_seconds=0.0)
    demo.register_agent("founder")
    demo.register_agent("trader")
    demo.deposit_fiat("founder", 1000)
    demo.deposit_fiat("trader", 20_000)
    coin = demo.launch_aicoin("GEM", "Gem", "founder", 10_000, 1000, 0.1)
    assert any(p.category == "N-AICoin" for p in demo.seepnews.posts)

    for _ in range(200):
        try:
            demo.buy("trader", coin.coin_id, 200)
        except Exception:
            break
    assert coin.freeze.state == FreezeState.FROZEN
    assert any(p.category == "Freezes" for p in demo.seepnews.posts)

    demo.place_post_freeze_order("trader", coin.coin_id, "buy", coin.freeze.ceiling * 1.02, 100)
    assert any(p.category == "PostFreeze" for p in demo.seepnews.posts)


def test_post_freeze_uses_system_post_not_agent_cooldown():
    clock = ManualClock(0.0)
    demo = SynTrendsDemo(cooldown_seconds=5.0, clock=clock, seepnews_cooldown_seconds=3600.0)
    demo.register_agent("founder")
    demo.register_agent("trader")
    demo.deposit_fiat("founder", 1000)
    demo.deposit_fiat("trader", 20_000)
    coin = demo.launch_aicoin("GEM", "Gem", "founder", 10_000, 1000, 0.1)

    for _ in range(200):
        try:
            demo.buy("trader", coin.coin_id, 200)
        except Exception:
            break

    demo.place_post_freeze_order("trader", coin.coin_id, "buy", 1.5, 100)
    pfo_posts = [p for p in demo.seepnews.posts if p.category == "PostFreeze"]
    assert len(pfo_posts) == 1
    assert pfo_posts[0].agent_id is None


def test_body_locks_persist_through_state_io():
    clock = ManualClock(0.0)
    demo = SynTrendsDemo(clock=clock, seepnews_cooldown_seconds=60.0)
    demo.register_agent("a1")
    demo.seepnews.post("a1", "Trade", "persist me $GEM", mentions=["GEM"], hashtags=TAGS)
    assert demo.seepnews._body_locks

    data = dump_demo(demo, clock)
    restored = load_demo(data, ManualClock(clock()))
    assert restored.seepnews._body_locks == demo.seepnews._body_locks

    with pytest.raises(SeepnewsError, match="duplicate"):
        restored.seepnews.post("a2", "Trade", "persist me $GEM", mentions=["GEM"], hashtags=TAGS)


def test_digest_bot_publishes_after_interval():
    from chain.stp import ParsedTrade
    from demo.agents.digest_bot import DigestBot

    class FakeClient:
        def agree_syntrends(self):
            pass

        def agree_seepnews(self):
            pass

        def snapshot_records(self):
            return []

        posts: list = []

        def post_seepnews(self, category, body, mentions, hashtags=None):
            self.posts.append((category, body))
            return []

    client = FakeClient()
    bot = DigestBot("digest-test", client, digest_ticker="GEM", interval_seconds=3600.0)
    bot.bootstrap()

    trade = ParsedTrade(
        agent="trader-a", ticker="GEM", side="BUY", coins=100.0, fiat=50.0,
        fee=0.01, price_after=0.5, ts=100.0,
    )
    assert bot.on_records([trade]) == []

    trade2 = ParsedTrade(
        agent="trader-b", ticker="GEM", side="BUY", coins=50.0, fiat=25.0,
        fee=0.01, price_after=0.51, ts=2000.0,
    )
    assert bot.on_records([trade2]) == []
    assert client.posts == []

    trade3 = ParsedTrade(
        agent="trader-c", ticker="GEM", side="SELL", coins=10.0, fiat=5.0,
        fee=0.01, price_after=0.52, ts=3601.0,
    )
    bot.on_records([trade3])
    assert len(client.posts) == 1
    assert client.posts[0][0] == "System"
    assert "Hourly market digest" in client.posts[0][1]
