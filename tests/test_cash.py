import pytest

from chain.aicoin import AICoinError
from chain.cash import (
    CASH_KIND,
    CASH_UNIT,
    is_reserved_cash_ticker,
    normalize_ticker,
    reserved_ticker_error,
)
from chain.engine import SynTrendsDemo


def test_normalize_strips_dollar():
    assert normalize_ticker("$syntrends") == "SYNTRENDS"


def test_reserved_set():
    assert is_reserved_cash_ticker("syn")
    assert is_reserved_cash_ticker("$USD")
    assert not is_reserved_cash_ticker("GEM")


def test_engine_launch_reserved_raises():
    demo = SynTrendsDemo()
    demo.register_agent("a")
    demo.deposit_fiat("a", 10_000)
    with pytest.raises(AICoinError, match="cash chip"):
        demo.launch_aicoin("SYNTRENDS", "Nope", "a", 10_000, 1000, 0.1)


def test_error_mentions_unit():
    msg = reserved_ticker_error("usd")
    assert CASH_UNIT in msg
    assert CASH_KIND in msg
