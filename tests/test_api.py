"""Phase B HTTP API tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from chain.stp import CHANNEL_MARKET, CHANNEL_SEEPNEWS, filter_snapshot_lines, line_channel


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def keys(client: TestClient):
    resp = client.get("/demo/keys")
    assert resp.status_code == 200
    return resp.json()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health(client: TestClient):
    assert client.get("/health").json()["protocol"] == "STP/1.0"


def test_demo_keys_present(client: TestClient, keys: dict):
    assert keys["agent_key"].startswith("st_agent_")
    assert keys["thirdps_key"].startswith("st_thirdps_")
    assert keys["license_key"] == keys["thirdps_key"]


def test_snapshot_requires_auth(client: TestClient):
    assert client.get("/snapshot").status_code == 401


def test_thirdps_snapshot_market_only_no_wallets(client: TestClient, keys: dict):
    resp = client.get("/snapshot", headers=auth(keys["thirdps_key"]))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    assert body.startswith("STP/1.0")
    assert "ST/T TICKER=GEM" in body
    assert "ST/W " not in body


def test_agent_snapshot_includes_wallets(client: TestClient, keys: dict):
    resp = client.get("/snapshot", headers=auth(keys["agent_key"]))
    assert resp.status_code == 200
    assert "ST/W AGENT=" in resp.text


def test_agent_snapshot_includes_coin_wallet_after_buy(client: TestClient, keys: dict):
    headers = auth(keys["agent_key"])
    client.post("/trade/buy", headers=headers, json={"ticker": "GEM", "fiat_amount": 25.0})
    resp = client.get("/snapshot", headers=headers)
    assert resp.status_code == 200
    assert "ST/W AGENT=agent-trader-a TICKER=GEM BALANCE=" in resp.text


def test_agent_buy_emits_wallet_coin_line(client: TestClient, keys: dict):
    resp = client.post(
        "/trade/buy",
        headers=auth(keys["agent_key"]),
        json={"ticker": "GEM", "fiat_amount": 25.0},
    )
    assert resp.status_code == 200
    assert "ST/W AGENT=agent-trader-a TICKER=GEM BALANCE=" in resp.text


def test_thirdps_cannot_trade(client: TestClient, keys: dict):
    resp = client.post(
        "/trade/buy",
        headers=auth(keys["thirdps_key"]),
        json={"ticker": "GEM", "fiat_amount": 50.0},
    )
    assert resp.status_code == 403


def test_agent_buy_returns_stp_trade_lines(client: TestClient, keys: dict):
    snap_before = client.get("/snapshot", headers=auth(keys["agent_key"])).text
    resp = client.post(
        "/trade/buy",
        headers=auth(keys["agent_key"]),
        json={"ticker": "GEM", "fiat_amount": 25.0},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "TX/BUY" in resp.text
    assert "ST/T TICKER=GEM" in resp.text

    snap_after = client.get("/snapshot", headers=auth(keys["agent_key"])).text
    assert snap_before != snap_after


def test_agent_sell(client: TestClient, keys: dict):
    client.post("/trade/buy", headers=auth(keys["agent_key"]), json={"ticker": "GEM", "fiat_amount": 10.0})
    resp = client.post(
        "/trade/sell",
        headers=auth(keys["agent_key"]),
        json={"ticker": "GEM", "coin_amount": 1.0},
    )
    assert resp.status_code == 200
    assert "TX/SELL" in resp.text


DEFAULT_SEEP_HASHTAGS = ["trending", "syntrends", "seepnews"]


def test_seepnews_post(client: TestClient, keys: dict):
    client.post(
        "/seepnews/agree",
        headers=auth(keys["agent_key"]),
        json={"attestation": "I agree."},
    )
    resp = client.post(
        "/seepnews/post",
        headers=auth(keys["agent_key"]),
        json={
            "category": "Trade",
            "body": "Watching $GEM momentum today",
            "mentions": ["GEM"],
            "hashtags": ["trending", "syntrends", "seepnews"],
        },
    )
    assert resp.status_code == 200
    assert "SN/[Trade]" in resp.text
    assert "TICKER=GEM" in resp.text


def test_stream_market_tail(client: TestClient, keys: dict):
    client.post("/trade/buy", headers=auth(keys["agent_key"]), json={"ticker": "GEM", "fiat_amount": 5.0})
    resp = client.get(
        "/stream/market?tail=5&live=0",
        headers=auth(keys["thirdps_key"]),
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    lines = [ln[6:] for ln in resp.text.splitlines() if ln.startswith("data: ")]
    assert lines
    assert all(ln.startswith(("ST/", "TX/", "LB/", "PFO/", "STP/", "ERR/", "BLK/")) for ln in lines)


def test_stream_seepnews_channel_filter():
    assert line_channel("SN/[Trade] POST_ID=x") == CHANNEL_SEEPNEWS
    assert line_channel("ST/T TICKER=GEM") == CHANNEL_MARKET
    assert line_channel("TX/BUY AGENT=a") == CHANNEL_MARKET


def test_filter_snapshot_lines_strips_wallets():
    lines = ["STP/1.0", "ST/W AGENT=a FIAT=1.0", "ST/T TICKER=GEM"]
    filtered = filter_snapshot_lines(lines, include_wallets=False)
    assert "ST/W" not in " ".join(filtered)
    assert "ST/T" in " ".join(filtered)


def test_broker_replay_respects_channel():
    from api.broker import STPStreamBroker

    broker = STPStreamBroker()
    broker.publish("ST/T TICKER=GEM")
    broker.publish("SN/[Trade] TICKER=GEM")
    market = broker.replay(CHANNEL_MARKET, broker.history)
    news = broker.replay(CHANNEL_SEEPNEWS, broker.history)
    assert any(ln.startswith("ST/T") for ln in market)
    assert all(ln.startswith("SN/") for ln in news)


def test_invalid_key_rejected(client: TestClient):
    assert client.get("/snapshot", headers=auth("st_agent_invalid")).status_code == 401


def test_launch_aicoin(client: TestClient, keys: dict):
    client.post(
        "/agent/deposit",
        headers=auth(keys["agent_key"]),
        json={"agent_id": "agent-trader-a", "amount": 500.0},
    )
    resp = client.post(
        "/aicoin/launch",
        headers=auth(keys["agent_key"]),
        json={
            "ticker": "CAT",
            "name": "Cat Coin",
            "total_supply": 5000,
            "invest_fiat": 100.0,
            "pre_own_pct": 0.05,
            "creator_agent_id": "agent-trader-a",
        },
    )
    assert resp.status_code == 200
    assert "ST/AICOIN TICKER=CAT" in resp.text
