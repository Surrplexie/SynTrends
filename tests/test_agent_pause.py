"""Phase J — owner pause / resume agent writes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.agent_pause import AgentPauseRegistry
from api.web_app import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _onboard_owner(client: TestClient, email: str, agent_id: str) -> tuple[str, str]:
    """Register owner, complete KYC, connect agent. Returns (session_token, api_key)."""
    reg = client.post(
        "/owners/api/register",
        json={"email": email, "password": "password123"},
    )
    assert reg.status_code == 200
    token = reg.json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    client.post("/owners/api/agreements/accept", headers=headers)
    client.post("/owners/api/syntrendrules/accept", headers=headers, json={"attestation": "I agree."})
    client.post("/owners/api/seeprules/accept", headers=headers, json={"attestation": "I agree."})
    client.post(
        "/owners/api/kyc/submit",
        headers=headers,
        json={"full_name": "Pause Tester", "country": "US", "attestation": True},
    )
    owner_id = client.get("/owners/api/me", headers=headers).json()["owner_id"]
    client.post("/owners/api/kyc/approve", json={"owner_id": owner_id})

    conn = client.post(
        "/owners/api/agents/connect",
        headers=headers,
        json={"agent_id": agent_id},
    )
    assert conn.status_code == 200
    api_key = conn.json()["api_key"]
    return token, api_key


def test_pause_blocks_trade_snapshot_still_works(client: TestClient):
    token, api_key = _onboard_owner(client, "pause1@test.example", "agent-pause-1")
    headers = {"Authorization": f"Bearer {token}"}
    agent_headers = {"Authorization": f"Bearer {api_key}"}

    client.post("/syntrends/agree", headers=agent_headers, json={"attestation": "I agree."})
    client.post("/seepnews/agree", headers=agent_headers, json={"attestation": "I agree."})

    pause = client.post(
        "/owners/api/agents/pause",
        headers=headers,
        json={"agent_id": "agent-pause-1"},
    )
    assert pause.status_code == 200
    assert pause.json()["paused"] is True
    assert pause.json()["writes_blocked"] is True

    me = client.get("/owners/api/me", headers=headers).json()
    assert me["agents"][0]["paused"] is True

    snap = client.get("/snapshot", headers=agent_headers)
    assert snap.status_code == 200
    assert snap.text.startswith("STP/1.0")

    buy = client.post(
        "/trade/buy",
        headers=agent_headers,
        json={"ticker": "GEM", "fiat_amount": 10.0},
    )
    assert buy.status_code == 200
    assert "AGENT_PAUSED" in buy.text

    resume = client.post(
        "/owners/api/agents/resume",
        headers=headers,
        json={"agent_id": "agent-pause-1", "gradual_seconds": 0},
    )
    assert resume.status_code == 200
    assert resume.json()["paused"] is False
    assert resume.json()["writes_blocked"] is False

    buy2 = client.post(
        "/trade/buy",
        headers=agent_headers,
        json={"ticker": "GEM", "fiat_amount": 10.0},
    )
    assert buy2.status_code == 200
    assert "AGENT_PAUSED" not in buy2.text


def test_pause_other_owners_agent_forbidden(client: TestClient):
    token, _ = _onboard_owner(client, "pause2a@test.example", "agent-pause-2a")
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/owners/api/agents/pause",
        headers=headers,
        json={"agent_id": "agent-not-mine"},
    )
    assert resp.status_code == 400
    assert "not linked" in resp.json()["detail"].lower()


def test_gradual_resume_blocks_writes_temporarily(client: TestClient):
    token, api_key = _onboard_owner(client, "pause3@test.example", "agent-pause-3")
    headers = {"Authorization": f"Bearer {token}"}
    agent_headers = {"Authorization": f"Bearer {api_key}"}

    client.post("/owners/api/agents/pause", headers=headers, json={"agent_id": "agent-pause-3"})
    client.post(
        "/owners/api/agents/resume",
        headers=headers,
        json={"agent_id": "agent-pause-3", "gradual_seconds": 60},
    )

    status = client.get("/owners/api/agents/status", headers=headers).json()
    assert status["agents"][0]["writes_blocked"] is True
    assert status["agents"][0]["paused"] is False


def test_agent_pause_registry_persistence_roundtrip():
    reg = AgentPauseRegistry()
    reg.pause("owner_a", "agent-x")
    exported = reg.export_state()
    reg2 = AgentPauseRegistry()
    reg2.import_state(exported)
    blocked, msg = reg2.write_block_reason("agent-x")
    assert blocked is True
    assert "paused" in msg


def test_pause_persists_across_service_reload(client: TestClient):
    token, api_key = _onboard_owner(client, "pause4@test.example", "agent-pause-4")
    headers = {"Authorization": f"Bearer {token}"}
    agent_headers = {"Authorization": f"Bearer {api_key}"}

    client.post("/syntrends/agree", headers=agent_headers, json={"attestation": "I agree."})
    client.post("/owners/api/agents/pause", headers=headers, json={"agent_id": "agent-pause-4"})

    from api.agent_routes import get_service

    svc = get_service()
    data = svc.export_snapshot()
    svc.import_snapshot(data)

    buy = client.post(
        "/trade/buy",
        headers=agent_headers,
        json={"ticker": "GEM", "fiat_amount": 5.0},
    )
    assert "AGENT_PAUSED" in buy.text
