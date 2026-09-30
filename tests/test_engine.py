"""End-to-end tests exercising SynTrendsDemo the way the scripted demo does:
register agents, deposit fiat, launch an AICoin, pump it into a freeze,
get rejected, place a Post-Freeze Order, let the cooldown lapse, fill the
order, mine a block, and confirm tamper detection still works.
"""

import pytest

from chain.clock import ManualClock
from chain.engine import SynTrendsDemo
from chain.freeze import FreezeState
from chain.orders import OrderError

MAX_PUMP_ATTEMPTS = 200


def make_demo():
    clock = ManualClock(0.0)
    demo = SynTrendsDemo(cooldown_seconds=5.0, pfo_timeout_seconds=30.0, seepnews_cooldown_seconds=0.1, clock=clock)
    demo.register_agent("founder")
    demo.register_agent("trader1")
    demo.deposit_fiat("founder", 1_000)
    demo.deposit_fiat("trader1", 20_000)
    coin = demo.launch_aicoin("GEM", "Gemstone", "founder", 10_000, 1_000, 0.1)
    return clock, demo, coin


def test_launch_credits_creator_wallet():
    clock, demo, coin = make_demo()
    assert demo.wallets.balance("founder", coin.coin_id) == pytest.approx(coin.creator_coins)
    assert demo.wallets.fiat_balance("founder") == pytest.approx(0.0)


def test_launch_posts_to_seepnews():
    clock, demo, coin = make_demo()
    feed = demo.seepnews.feed()
    assert any(p.category == "N-AICoin" for p in feed)


def test_buy_updates_price_without_seepnews_trade_post():
    clock, demo, coin = make_demo()
    feed_before = len(demo.seepnews.feed())
    fill = demo.buy("trader1", coin.coin_id, 100)
    assert fill.coin_amount > 0
    feed = demo.seepnews.feed()
    assert len(feed) == feed_before
    assert not any(p.category == "Trade" for p in feed)


def test_full_freeze_and_post_freeze_order_cycle():
    clock, demo, coin = make_demo()

    target = coin.launch_price * 11.24
    attempts = 0
    while coin.price < target and attempts < MAX_PUMP_ATTEMPTS:
        demo.buy("trader1", coin.coin_id, 200)
        attempts += 1
    assert coin.freeze.state == FreezeState.FROZEN
    assert any(p.category == "Freezes" for p in demo.seepnews.feed())

    with pytest.raises(OrderError):
        demo.buy("trader1", coin.coin_id, 200)

    order = demo.place_post_freeze_order("trader1", coin.coin_id, "buy", coin.freeze.ceiling * 1.02, 200)

    clock.advance(6.0)  # cooldown elapses
    demo.tick(coin.coin_id)
    assert coin.freeze.state == FreezeState.GROWING

    attempts = 0
    while coin.price < order.target_price and attempts < MAX_PUMP_ATTEMPTS:
        demo.buy("trader1", coin.coin_id, 50)
        demo.tick(coin.coin_id)
        attempts += 1
    demo.tick(coin.coin_id)

    assert order.status == "filled"


def test_mining_and_chain_validity():
    clock, demo, coin = make_demo()
    demo.buy("trader1", coin.coin_id, 100)
    block = demo.mine_block()
    assert block is not None
    assert demo.chain.is_valid()


def test_tamper_detected_end_to_end():
    clock, demo, coin = make_demo()
    demo.buy("trader1", coin.coin_id, 100)
    demo.mine_block()
    demo.chain.chain[-1].transactions[0].payload["fiat_amount"] = 999_999
    assert not demo.chain.is_valid()


def test_leaderboard_orders_by_market_cap():
    clock, demo, coin = make_demo()
    demo.deposit_fiat("founder", 100)
    demo.launch_aicoin("DOG", "Doggy", "founder", 10_000, 100, 0.05)
    board = demo.leaderboard(by="market_cap")
    assert board[0].coin_id == coin.coin_id  # $1,000 mcap > $100 mcap


def test_unknown_coin_id_raises():
    clock, demo, coin = make_demo()
    from chain.aicoin import AICoinError
    with pytest.raises(AICoinError):
        demo.buy("trader1", "not-a-real-coin-id", 100)
