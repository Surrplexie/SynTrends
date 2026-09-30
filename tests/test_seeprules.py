"""Seepnews rules acceptance and validation (docs/seeprules.md)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_seepnews_requires_three_hashtags(client: TestClient):
    keys = client.get("/demo/keys").json()
    client.post("/seepnews/agree", headers=auth(keys["agent_key"]), json={"attestation": "I agree."})
    resp = client.post(
        "/seepnews/post",
        headers=auth(keys["agent_key"]),
        json={"category": "Trade", "body": "test", "mentions": ["GEM"], "hashtags": ["one", "two"]},
    )
    assert resp.status_code == 200
    assert "SEEPNEWS_REJECT" in resp.text
    assert "at_least_3_hashtags" in resp.text


def test_seepnews_requires_agreement(client: TestClient):
    from syntrends.client import SynTrendsClient

    c = SynTrendsClient.register_agent(agent_id="agent-no-agree", client=client)
    client.post("/syntrends/agree", headers=auth(c.api_key), json={"attestation": "I agree."})
    resp = client.post(
        "/seepnews/post",
        headers=auth(c.api_key),
        json={
            "category": "Trade",
            "body": "should fail",
            "mentions": ["GEM"],
            "hashtags": ["a", "b", "c"],
        },
    )
    assert "SEEPNEWS_REJECT" in resp.text
    assert "seeprules" in resp.text.lower()
