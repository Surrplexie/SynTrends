"""Owner $syntrends chip pool: credit (simulated), allocate, recall."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app_factory import create_app
from api.config import Settings
from api.owner_cash import OwnerCashError, OwnerCashLedger
from api.web_app import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _onboard_owner(client: TestClient, email: str, agent_id: str) -> tuple[str, str]:
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
        json={"full_name": "Cash Tester", "country": "US", "attestation": True},
    )
    owner_id = client.get("/owners/api/me", headers=headers).json()["owner_id"]
    client.post("/owners/api/kyc/approve", json={"owner_id": owner_id})
    conn = client.post(
        "/owners/api/agents/connect",
        headers=headers,
        json={"agent_id": agent_id},
    )
    assert conn.status_code == 200
    return token, conn.json()["api_key"]


def test_ledger_credit_allocate_recall_roundtrip():
    led = OwnerCashLedger()
    led.credit("ow1", 100.0)
    assert led.balance("ow1") == 100.0
    led.debit_owner("ow1", 40.0)
    led.record_allocate("ow1", "agent-a", 40.0)
    assert led.balance("ow1") == 60.0
    led.credit_owner_only("ow1", 15.0)
    led.record_recall("ow1", "agent-a", 15.0)
    assert led.balance("ow1") == 75.0
    blob = led.export_state()
    other = OwnerCashLedger()
    other.import_state(blob)
    assert other.balance("ow1") == 75.0
    kinds = [e.kind for e in other.entries_for("ow1")]
    assert kinds == ["credit", "allocate", "recall"]
    with pytest.raises(OwnerCashError):
        led.debit_owner("ow1", 10_000)


def test_owner_credit_allocate_recall_and_agent_wallet(client: TestClient):
    token, api_key = _onboard_owner(client, "cash1@test.example", "agent-cash-1")
    headers = {"Authorization": f"Bearer {token}"}
    agent_headers = {"Authorization": f"Bearer {api_key}"}

    cfg = client.get("/owners/api/config").json()
    assert cfg["owner_cash_credit_enabled"] is True
    assert cfg["cash_unit"] == "SYNTRENDS"

    empty = client.get("/owners/api/cash", headers=headers).json()
    assert empty["owner_balance"] == 0
    assert empty["display"] == "$syntrends"
    assert empty["simulated_credit_enabled"] is True

    credit = client.post("/owners/api/cash/credit", headers=headers, json={})
    assert credit.status_code == 200, credit.text
    body = credit.json()
    assert body["owner_balance"] == 5000.0
    assert body["recent"][-1]["kind"] == "credit"

    again = client.post("/owners/api/cash/credit", headers=headers, json={})
    assert again.status_code == 400
    assert "cooldown" in again.json()["detail"].lower()

    alloc = client.post(
        "/owners/api/cash/allocate",
        headers=headers,
        json={"agent_id": "agent-cash-1", "amount": 100},
    )
    assert alloc.status_code == 200, alloc.text
    assert alloc.json()["owner_balance"] == 4900.0
    agent_row = next(a for a in alloc.json()["agents"] if a["agent_id"] == "agent-cash-1")
    assert agent_row["cash"] == 100.0

    snap = client.get("/snapshot", headers=agent_headers)
    assert snap.status_code == 200
    assert "UNIT=SYNTRENDS" in snap.text
    assert "KIND=chip" in snap.text
    assert "agent-cash-1" in snap.text

    other = client.post(
        "/owners/api/cash/allocate",
        headers=headers,
        json={"agent_id": "agent-not-mine", "amount": 1},
    )
    assert other.status_code == 400
    assert "not linked" in other.json()["detail"].lower()

    over = client.post(
        "/owners/api/cash/allocate",
        headers=headers,
        json={"agent_id": "agent-cash-1", "amount": 99_999},
    )
    assert over.status_code == 400

    recall = client.post(
        "/owners/api/cash/recall",
        headers=headers,
        json={"agent_id": "agent-cash-1", "amount": 40},
    )
    assert recall.status_code == 200, recall.text
    assert recall.json()["owner_balance"] == 4940.0
    agent_row = next(a for a in recall.json()["agents"] if a["agent_id"] == "agent-cash-1")
    assert agent_row["cash"] == 60.0

    too_much = client.post(
        "/owners/api/cash/recall",
        headers=headers,
        json={"agent_id": "agent-cash-1", "amount": 10_000},
    )
    assert too_much.status_code == 400


def test_live_network_rejects_simulated_owner_credit():
    settings = Settings(env="production", faucet_enabled=True, allow_sandbox_deposit=True)
    live_app = create_app(require_owner_kyc=True, mount_web=True, settings=settings)
    with TestClient(live_app) as client:
        cfg = client.get("/owners/api/config").json()
        assert cfg["owner_cash_credit_enabled"] is False
        reg = client.post(
            "/owners/api/register",
            json={"email": "cash-live@test.example", "password": "password123"},
        )
        assert reg.status_code == 200
        headers = {"Authorization": f"Bearer {reg.json()['session_token']}"}
        resp = client.post("/owners/api/cash/credit", headers=headers, json={})
        assert resp.status_code == 403
        assert "partner" in resp.json()["detail"].lower()
    create_app(require_owner_kyc=True, mount_web=True)
