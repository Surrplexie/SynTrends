"""Phase D tests: human web sites, owner KYC flow, KYC-gated keys."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.web_app import app

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"

FORBIDDEN_HUMAN_PATTERNS = re.compile(
    r"AICoin|aicoin|\$GEM|ticker|mcap|market cap|freeze cycle|order book|"
    r"Seepnews feed|SN/\[|ST/T |leaderboard|candle|price chart",
    re.I,
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _human_html_paths() -> list[Path]:
    paths = []
    for sub in ("syntrends", "seepnews", "owners"):
        root = WEB_ROOT / sub
        if root.is_dir():
            paths.extend(root.glob("*.html"))
    return paths


@pytest.mark.parametrize("html_path", _human_html_paths(), ids=lambda p: p.name)
def test_human_pages_contain_no_market_or_feed_content(html_path: Path):
    text = html_path.read_text(encoding="utf-8")
    assert not FORBIDDEN_HUMAN_PATTERNS.search(text), f"{html_path.name} mentions market/feed content"


def test_syntrends_home_deep_links_testnet_owners(client: TestClient):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "https://testnet.syntrends.com/owners/" in resp.text
    js = client.get("/shared/portal-link.js")
    assert js.status_code == 200
    assert "data-portal" in js.text


def test_disclaimer_page_served(client: TestClient):
    resp = client.get("/disclaimer.html")
    assert resp.status_code == 200
    text = resp.text.lower()
    assert "not a contract" in text
    assert "bitcoin" in text
    assert "3rdps" in text or "third-party" in text

    seep = client.get("/seepnews/disclaimer.html")
    assert seep.status_code == 200
    assert "disclaimer" in seep.text.lower()


def test_seepnews_home_served(client: TestClient):
    resp = client.get("/seepnews/")
    assert resp.status_code == 200
    assert "does not publish" in resp.text.lower()


def test_well_known(client: TestClient):
    data = client.get("/.well-known/syntrends").json()
    assert data["protocol"] == "STP/1.0"
    apis = data["apis"]
    assert apis["agent_api"]["key_prefix"] == "st_agent_*"
    assert apis["thirdps_api"]["key_prefix"] == "st_thirdps_*"
    assert apis["agent_api"]["writes"] is True
    assert apis["thirdps_api"]["writes"] is False
    lifecycle = data["key_lifecycle"]
    assert lifecycle["agent_api"]["expires"] is False
    assert lifecycle["thirdps_api"]["expires"] is True
    assert lifecycle["thirdps_api"]["issuance_fee"] == 0
    assert "Curation Tokens" in lifecycle["thirdps_api"]["billing"]
    assert "api_turning" in lifecycle
    assert lifecycle["api_turning"]["scope"].startswith("All API keys")


def test_demo_keys_hidden_when_kyc_required(client: TestClient):
    assert client.get("/demo/keys").status_code == 404


def test_owner_register_accept_kyc_connect_agent(client: TestClient):
    reg = client.post("/owners/api/register", json={"email": "owner@test.example", "password": "password123"})
    assert reg.status_code == 200
    token = reg.json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    client.post("/owners/api/agreements/accept", headers=headers)
    client.post("/owners/api/syntrendrules/accept", headers=headers, json={"attestation": "I agree."})
    client.post("/owners/api/seeprules/accept", headers=headers, json={"attestation": "I agree."})
    client.post(
        "/owners/api/kyc/submit",
        headers=headers,
        json={"full_name": "Test Owner", "country": "US", "attestation": True},
    )
    owner_id = client.get("/owners/api/me", headers=headers).json()["owner_id"]
    client.post("/owners/api/kyc/approve", json={"owner_id": owner_id})

    conn = client.post(
        "/owners/api/agents/connect",
        headers=headers,
        json={"agent_id": "agent-phase-d-test"},
    )
    assert conn.status_code == 200
    assert conn.json()["api_key"].startswith("st_agent_")

    snap = client.get("/snapshot", headers={"Authorization": f"Bearer {conn.json()['api_key']}"})
    assert snap.status_code == 200
    assert snap.text.startswith("STP/1.0")


def test_keys_agent_requires_owner_session_when_kyc_enabled(client: TestClient):
    resp = client.post("/keys/agent", json={"agent_id": "agent-no-owner"})
    assert resp.status_code == 401


def test_explorer_page_served(client: TestClient):
    resp = client.get("/explorer/")
    assert resp.status_code == 200
    assert "block explorer" in resp.text.lower()


def test_vendor_page_served(client: TestClient):
    resp = client.get("/vendor/")
    assert resp.status_code == 200
    assert "thirdps" in resp.text.lower()
