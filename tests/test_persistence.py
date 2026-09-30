"""Tests for SQLite persistence and tax export (Phase E)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.persistence import Persistence
from api.service import SynTrendsAPIService
from api.tax import render_tax_csv
from api.app_factory import create_app, get_service


@pytest.fixture
def sqlite_url(tmp_path: Path):
    return f"sqlite:///{tmp_path / 'test.db'}"


def test_persistence_save_load_roundtrip(sqlite_url: str):
    p = Persistence(sqlite_url)
    svc = SynTrendsAPIService(persistence=p)
    svc.seed_demo()
    svc.persist()

    svc2 = SynTrendsAPIService(persistence=p)
    keys = svc2.load_or_seed()
    assert keys["restored"] is True
    assert len(svc2.demo.chain.chain) >= 1
    assert "agent-trader-a" in svc2.demo.agents


def test_load_or_seed_fresh_when_empty(sqlite_url: str):
    p = Persistence(sqlite_url)
    svc = SynTrendsAPIService(persistence=p)
    keys = svc.load_or_seed()
    assert keys["restored"] is False
    assert keys["agent_key"].startswith("st_agent_")


def test_tax_csv_includes_trades():
    svc = SynTrendsAPIService()
    svc.seed_demo()
    gem = next(c for c in svc.demo.coins.values() if c.ticker == "GEM")
    svc.demo.buy("agent-trader-a", gem.coin_id, 50)
    svc.demo.mine_block()
    csv_text = render_tax_csv(svc.demo, ["agent-trader-a"])
    assert "datetime,agent_id,ticker" in csv_text
    assert "agent-trader-a" in csv_text
    assert "DISCLAIMER" in csv_text


def test_tax_csv_excludes_pending_trades():
    svc = SynTrendsAPIService()
    svc.seed_demo()
    gem = next(c for c in svc.demo.coins.values() if c.ticker == "GEM")
    svc.demo.buy("agent-trader-a", gem.coin_id, 50)
    assert svc.demo.chain.pending
    csv_text = render_tax_csv(svc.demo, ["agent-trader-a"])
    data_lines = [ln for ln in csv_text.splitlines()[1:] if ln and not ln.startswith("DISCLAIMER")]
    assert not any("agent-trader-a" in ln for ln in data_lines)


def test_tax_export_owner_route(sqlite_url: str):
    app = create_app(require_owner_kyc=True, mount_web=True, database_url=sqlite_url)
    with TestClient(app) as client:
        reg = client.post("/owners/api/register", json={"email": "tax@test.example", "password": "password123"})
        token = reg.json()["session_token"]
        headers = {"Authorization": f"Bearer {token}"}
        client.post("/owners/api/agreements/accept", headers=headers)
        client.post("/owners/api/syntrendrules/accept", headers=headers, json={"attestation": "I agree."})
        client.post("/owners/api/seeprules/accept", headers=headers, json={"attestation": "I agree."})
        client.post(
            "/owners/api/kyc/submit",
            headers=headers,
            json={"full_name": "Tax Owner", "country": "US", "attestation": True},
        )
        owner_id = client.get("/owners/api/me", headers=headers).json()["owner_id"]
        client.post("/owners/api/kyc/approve", json={"owner_id": owner_id})
        conn = client.post("/owners/api/agents/connect", headers=headers, json={"agent_id": "agent-trader-a"})
        assert conn.status_code == 200

        demo_svc = get_service()
        gem = next(c for c in demo_svc.demo.coins.values() if c.ticker == "GEM")
        demo_svc.demo.buy("agent-trader-a", gem.coin_id, 25)
        demo_svc.demo.mine_block()

        resp = client.get("/owners/api/tax/export", headers=headers)
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        assert b"agent-trader-a" in resp.content


def test_explorer_api_summary():
    app = create_app(require_owner_kyc=True, mount_web=True)
    with TestClient(app) as client:
        data = client.get("/explorer/api/summary").json()
        assert "blocks" in data
        assert data["valid"] is True
