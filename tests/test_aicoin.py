import pytest

from chain.aicoin import AICoinError, create_aicoin
from chain.clock import ManualClock


def test_launch_matches_spec_worked_example():
    """syntrends.txt: 499k coins, $50k pool, 15% pre-own -> $0.1002/coin,
    holder owns 74,850 coins (15%) valued at $7,500, pool value $42,500.
    """
    coin = create_aicoin("GEM", "Gemstone", "founder", 499_000, 50_000, 0.15, clock=ManualClock(0.0))

    assert coin.launch_price == pytest.approx(0.1002004, rel=1e-4)
    assert coin.creator_coins == pytest.approx(74_850)
    assert coin.market_cap == pytest.approx(50_000, rel=1e-6)
    assert coin.creator_coins * coin.price == pytest.approx(7_500, rel=1e-6)
    assert coin.pool_fiat_reserve == pytest.approx(42_500, rel=1e-6)
    assert coin.pool_coin_reserve == pytest.approx(424_150)


def test_zero_pre_own_puts_everything_in_the_pool():
    coin = create_aicoin("X", "X", "f", 10_000, 1_000, 0.0, clock=ManualClock(0.0))
    assert coin.creator_coins == 0
    assert coin.pool_coin_reserve == 10_000
    assert coin.pool_fiat_reserve == pytest.approx(1_000)


def test_max_pre_own_21_percent_allowed():
    coin = create_aicoin("X", "X", "f", 10_000, 1_000, 0.21, clock=ManualClock(0.0))
    assert coin.creator_coins == pytest.approx(2_100)


def test_pre_own_pct_bounds_enforced():
    with pytest.raises(AICoinError):
        create_aicoin("X", "X", "f", 10_000, 1_000, 0.22)
    with pytest.raises(AICoinError):
        create_aicoin("X", "X", "f", 10_000, 1_000, -0.01)


def test_min_supply_enforced():
    with pytest.raises(AICoinError):
        create_aicoin("X", "X", "f", 500, 1_000, 0.1)


def test_invest_fiat_bounds_enforced():
    with pytest.raises(AICoinError):
        create_aicoin("X", "X", "f", 10_000, 50, 0.1)
    with pytest.raises(AICoinError):
        create_aicoin("X", "X", "f", 10_000, 600_000_000, 0.1)


def test_reserved_cash_tickers_cannot_launch():
    for ticker in ("SYNTRENDS", "$syntrends", "USD", "fiat"):
        with pytest.raises(AICoinError, match="cash chip"):
            create_aicoin(ticker, "Nope", "f", 10_000, 1_000, 0.1)


def test_ticker_is_uppercased():
    coin = create_aicoin("gem", "Gemstone", "f", 10_000, 1_000, 0.1, clock=ManualClock(0.0))
    assert coin.ticker == "GEM"


def test_freeze_engine_starts_at_launch_price():
    coin = create_aicoin("GEM", "Gemstone", "f", 10_000, 1_000, 0.1, clock=ManualClock(0.0))
    assert coin.freeze.start_price == pytest.approx(coin.launch_price)
