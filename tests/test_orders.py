import pytest

from chain.aicoin import create_aicoin
from chain.block import SynTrendsChain
from chain.clock import ManualClock
from chain.fees import FeeEngine
from chain.freeze import FreezeState
from chain.orders import OrderError, PostFreezeOrderBook, TradingEngine
from chain.wallet import WalletRegistry

MAX_PUMP_ATTEMPTS = 200


def make_engine(cooldown_seconds=5.0):
    clock = ManualClock(0.0)
    wallets = WalletRegistry()
    fees = FeeEngine(clock=clock)
    chain = SynTrendsChain()
    trading = TradingEngine(wallets, fees, chain, clock=clock)
    # Deliberately thin pool so a handful of demo-sized buys can pump 1024%.
    coin = create_aicoin(
        "GEM", "Gemstone", "founder", 10_000, 1_000, 0.1,
        cooldown_seconds=cooldown_seconds, clock=clock,
    )
    wallets.deposit_fiat("trader1", 20_000)
    wallets.deposit_fiat("trader2", 20_000)
    return clock, wallets, fees, chain, trading, coin


def pump_to_freeze(trading, coin, agent_id="trader1", increment=200.0):
    target = coin.launch_price * 11.24
    attempts = 0
    while coin.price < target and attempts < MAX_PUMP_ATTEMPTS:
        trading.buy(agent_id, coin, increment)
        attempts += 1
    assert coin.freeze.state == FreezeState.FROZEN, "failed to reach freeze within attempt budget"
    return attempts


def test_buy_increases_price_and_credits_coins():
    clock, wallets, fees, chain, trading, coin = make_engine()
    price_before = coin.price
    fill = trading.buy("trader1", coin, 100)
    assert coin.price > price_before
    assert wallets.balance("trader1", coin.coin_id) == pytest.approx(fill.coin_amount)
    assert fill.fee_paid > 0


def test_insufficient_fiat_raises():
    clock, wallets, fees, chain, trading, coin = make_engine()
    with pytest.raises(OrderError):
        trading.buy("trader1", coin, 10_000_000)


def test_sell_returns_fiat_and_zeroes_balance():
    clock, wallets, fees, chain, trading, coin = make_engine()
    trading.buy("trader1", coin, 100)
    held = wallets.balance("trader1", coin.coin_id)
    fiat_before = wallets.fiat_balance("trader1")
    trading.sell("trader1", coin, held)
    assert wallets.fiat_balance("trader1") > fiat_before
    assert wallets.balance("trader1", coin.coin_id) == pytest.approx(0.0, abs=1e-6)


def test_sell_more_than_held_raises():
    clock, wallets, fees, chain, trading, coin = make_engine()
    with pytest.raises(OrderError):
        trading.sell("trader1", coin, 1.0)


def test_buy_rejected_once_frozen():
    clock, wallets, fees, chain, trading, coin = make_engine()
    pump_to_freeze(trading, coin)
    with pytest.raises(OrderError):
        trading.buy("trader2", coin, 500)


def test_sell_allowed_while_frozen():
    clock, wallets, fees, chain, trading, coin = make_engine()
    pump_to_freeze(trading, coin)
    held = wallets.balance("trader1", coin.coin_id)
    trading.sell("trader1", coin, held * 0.1)  # must not raise


def test_freeze_lifts_after_cooldown():
    clock, wallets, fees, chain, trading, coin = make_engine(cooldown_seconds=5.0)
    pump_to_freeze(trading, coin)
    clock.advance(6.0)
    coin.freeze.tick(coin.price)
    assert coin.freeze.state == FreezeState.GROWING


def test_trades_are_logged_on_chain():
    clock, wallets, fees, chain, trading, coin = make_engine()
    trading.buy("trader1", coin, 100)
    block = chain.mine_block()
    assert any(tx.tx_type == "trade" for tx in block.transactions)


def test_post_freeze_order_requires_active_freeze():
    clock, wallets, fees, chain, trading, coin = make_engine()
    pfo = PostFreezeOrderBook(timeout_seconds=10.0, clock=clock)
    with pytest.raises(OrderError):
        pfo.place("trader1", coin, "buy", coin.price * 2, 100)


def test_post_freeze_order_fcfs_queue_order():
    clock, wallets, fees, chain, trading, coin = make_engine()
    pump_to_freeze(trading, coin)
    pfo = PostFreezeOrderBook(timeout_seconds=100.0, clock=clock)

    order1 = pfo.place("trader1", coin, "buy", coin.freeze.ceiling * 1.05, 100)
    clock.advance(0.5)
    order2 = pfo.place("trader2", coin, "buy", coin.freeze.ceiling * 1.05, 100)

    queue = pfo.queue(coin.coin_id)
    assert [o.order_id for o in queue] == [order1.order_id, order2.order_id]


def test_post_freeze_order_editing_resets_queue_position():
    clock, wallets, fees, chain, trading, coin = make_engine()
    pump_to_freeze(trading, coin)
    pfo = PostFreezeOrderBook(timeout_seconds=100.0, clock=clock)

    pfo.place("trader1", coin, "buy", coin.freeze.ceiling * 1.05, 100)
    clock.advance(0.5)
    pfo.place("trader2", coin, "buy", coin.freeze.ceiling * 1.05, 100)
    clock.advance(0.5)
    pfo.place("trader1", coin, "buy", coin.freeze.ceiling * 1.05, 150)  # edit -> back of queue

    queue = pfo.queue(coin.coin_id)
    assert [o.agent_id for o in queue] == ["trader2", "trader1"]
    assert queue[1].amount == 150  # latest edit took effect


def test_post_freeze_order_fills_once_price_reached():
    clock, wallets, fees, chain, trading, coin = make_engine()
    pump_to_freeze(trading, coin)
    pfo = PostFreezeOrderBook(timeout_seconds=100.0, clock=clock)
    order = pfo.place("trader2", coin, "buy", coin.freeze.ceiling * 1.02, 100)

    clock.advance(6.0)  # cooldown ends
    coin.freeze.tick(coin.price)
    assert coin.freeze.state == FreezeState.GROWING

    attempts = 0
    while coin.price < order.target_price and attempts < MAX_PUMP_ATTEMPTS:
        trading.buy("trader1", coin, 50)
        coin.freeze.tick(coin.price)
        attempts += 1

    pfo.resolve(coin, trading)
    assert order.status == "filled"
    assert order.filled_amount == 100


def test_post_freeze_order_expires_and_refunds():
    clock, wallets, fees, chain, trading, coin = make_engine()
    pump_to_freeze(trading, coin)
    pfo = PostFreezeOrderBook(timeout_seconds=5.0, clock=clock)
    order = pfo.place("trader2", coin, "buy", coin.freeze.ceiling * 10, 100)  # unreachable target

    clock.advance(6.0)
    pfo.resolve(coin, trading)
    assert order.status == "refunded"


def test_post_freeze_sell_order():
    clock, wallets, fees, chain, trading, coin = make_engine()
    pump_to_freeze(trading, coin)
    held = wallets.balance("trader1", coin.coin_id)

    pfo = PostFreezeOrderBook(timeout_seconds=100.0, clock=clock)
    sell_target = coin.price * 0.5
    order = pfo.place("trader1", coin, "sell", sell_target, held * 0.1)

    clock.advance(6.0)
    coin.freeze.tick(coin.price)

    # crash the price by having trader1 sell down their own stack.
    attempts = 0
    while coin.price > sell_target and attempts < MAX_PUMP_ATTEMPTS:
        try:
            trading.sell("trader1", coin, held * 0.02)
        except OrderError:
            break
        coin.freeze.tick(coin.price)
        attempts += 1

    pfo.resolve(coin, trading)
    assert order.status in ("filled", "refunded")
