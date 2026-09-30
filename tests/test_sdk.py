"""Phase C SDK tests: SynTrendsClient against the in-process Phase B API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from chain.stp import ParsedError, ParsedTicker, ParsedTrade
from syntrends.client import SynTrendsClient
from syntrends.errors import AuthenticationError, ForbiddenError
from syntrends.state import MarketView


@pytest.fixture
def tc():
    with TestClient(app) as c:
        yield c


def test_register_agent_bootstraps_key_and_client(tc: TestClient):
    client = SynTrendsClient.register_agent(agent_id="agent-sdk-test", client=tc)
    assert client.api_key.startswith("st_agent_")
    records = client.snapshot_records()
    assert any(isinstance(r, ParsedTicker) for r in records)


def test_issue_thirdps_client_is_read_only(tc: TestClient):
    client = SynTrendsClient.issue_thirdps_client(client=tc, label="sdk test vendor")
    assert client.api_key.startswith("st_thirdps_")
    with pytest.raises(ForbiddenError):
        client.buy(ticker="GEM", fiat_amount=10.0)


def test_invalid_key_raises_authentication_error(tc: TestClient):
    client = SynTrendsClient(api_key="st_agent_bogus", client=tc)
    with pytest.raises(AuthenticationError):
        client.snapshot()


def test_snapshot_view_builds_market_view(tc: TestClient):
    client = SynTrendsClient.register_agent(agent_id="agent-sdk-view", client=tc)
    view = client.snapshot_view()
    assert isinstance(view, MarketView)
    assert view.price("GEM") is not None
    assert view.price("GEM") > 0


def test_deposit_buy_sell_roundtrip(tc: TestClient):
    client = SynTrendsClient.register_agent(agent_id="agent-sdk-trader", client=tc)
    client.agree_syntrends()
    client.deposit("agent-sdk-trader", 5_000.0)

    buy_records = client.buy(ticker="GEM", fiat_amount=100.0)
    trades = [r for r in buy_records if isinstance(r, ParsedTrade)]
    assert trades and trades[0].side == "BUY"

    view = MarketView()
    view.apply_many(buy_records)
    assert view.coin_balance("agent-sdk-trader", "GEM") > 0
    assert view.fiat_balance("agent-sdk-trader") < 5000.0

    sell_records = client.sell(ticker="GEM", coin_amount=1.0)
    sells = [r for r in sell_records if isinstance(r, ParsedTrade)]
    assert sells and sells[0].side == "SELL"


def test_snapshot_view_includes_coin_balance_after_buy(tc: TestClient):
    client = SynTrendsClient.register_agent(agent_id="agent-sdk-coins", client=tc)
    client.agree_syntrends()
    client.deposit("agent-sdk-coins", 5_000.0)
    client.buy(ticker="GEM", fiat_amount=50.0)
    view = client.snapshot_view()
    assert view.coin_balance("agent-sdk-coins", "GEM") > 0


def test_launch_aicoin_via_sdk(tc: TestClient):
    client = SynTrendsClient.register_agent(agent_id="agent-sdk-founder", client=tc)
    client.agree_syntrends()
    client.deposit("agent-sdk-founder", 1_000.0)
    records = client.launch_aicoin("SDK", "SDK Coin", 5_000, 200.0, 0.05, "agent-sdk-founder")
    assert any(r.__class__.__name__ == "ParsedAICoinLaunch" for r in records)


def test_place_pfo_requires_active_freeze(tc: TestClient):
    client = SynTrendsClient.register_agent(agent_id="agent-sdk-pfo", client=tc)
    client.agree_syntrends()
    client.deposit("agent-sdk-pfo", 5_000.0)
    records = client.place_pfo(ticker="GEM", side="buy", target_price=999.0, amount=50.0)
    errors = [r for r in records if isinstance(r, ParsedError)]
    assert errors, "placing a PFO without an active freeze should be rejected"


def test_post_seepnews_via_sdk(tc: TestClient):
    client = SynTrendsClient.register_agent(agent_id="agent-sdk-poster", client=tc)
    client.agree_syntrends()
    client.agree_seepnews()
    records = client.post_seepnews(
        "Trade", "SDK smoke test post", mentions=["GEM"], hashtags=["trending", "syntrends", "seepnews"]
    )
    assert any(r.__class__.__name__ == "ParsedSeepnews" for r in records)


def test_tick_via_sdk_returns_ticker_lines(tc: TestClient):
    client = SynTrendsClient.register_agent(agent_id="agent-sdk-ticker", client=tc)
    client.agree_syntrends()
    records = client.tick(ticker="GEM")
    assert any(isinstance(r, ParsedTicker) for r in records)


def test_stream_market_replay_only(tc: TestClient):
    client = SynTrendsClient.register_agent(agent_id="agent-sdk-stream", client=tc)
    client.agree_syntrends()
    client.deposit("agent-sdk-stream", 1_000.0)
    client.buy(ticker="GEM", fiat_amount=20.0)
    records = list(client.stream_market(tail=10, live=False))
    assert records
    assert all(not isinstance(r, type(None)) for r in records)


def test_stream_seepnews_replay_only(tc: TestClient):
    client = SynTrendsClient.register_agent(agent_id="agent-sdk-news", client=tc)
    client.agree_syntrends()
    client.agree_seepnews()
    client.post_seepnews(
        "Trade", "hello from the SDK", mentions=["GEM"], hashtags=["trending", "syntrends", "seepnews"]
    )
    records = list(client.stream_seepnews(tail=20, live=False))
    assert any(r.__class__.__name__ == "ParsedSeepnews" for r in records)


def test_client_context_manager_closes_owned_client():
    with SynTrendsClient(base_url="http://127.0.0.1:9", api_key="unused") as client:
        assert client._owns_client is True
    # closing twice (via __exit__ already run) should not raise
