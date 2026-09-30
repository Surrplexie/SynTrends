"""SynTrends platform terms acceptance (docs/syntrendrules.md)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from syntrends.client import SynTrendsClient


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_trade_requires_syntrendrules_agreement(client: TestClient):
    c = SynTrendsClient.register_agent(agent_id="agent-no-st-rules", client=client)
    resp = client.post(
        "/trade/buy",
        headers=auth(c.api_key),
        json={"ticker": "GEM", "fiat_amount": 5.0},
    )
    assert resp.status_code == 200
    assert "SYNTRULES_REJECT" in resp.text
    assert "syntrendrules" in resp.text.lower()


def test_syntrends_agree_then_trade(client: TestClient):
    c = SynTrendsClient.register_agent(agent_id="agent-st-agreed", client=client)
    client.post("/syntrends/agree", headers=auth(c.api_key), json={"attestation": "I agree."})
    c.deposit("agent-st-agreed", 500.0)
    resp = client.post(
        "/trade/buy",
        headers=auth(c.api_key),
        json={"ticker": "GEM", "fiat_amount": 5.0},
    )
    assert "TX/BUY" in resp.text or "ORDER_REJECT" in resp.text
    assert "SYNTRULES_REJECT" not in resp.text
