"""Phase G — public testnet, faucet, status, key revocation, passwords."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from api.app_factory import create_app
from api.auth import KeyStore
from api.config import Settings
from api.passwords import hash_password, needs_rehash, verify_password
from api.service import FaucetError, SynTrendsAPIService
from chain.clock import ManualClock
from chain.node import ChainNode


def test_scrypt_password_hash_and_verify():
    stored = hash_password("securepass1")
    assert stored.startswith("scrypt:")
    assert verify_password("securepass1", stored)
    assert not verify_password("wrong", stored)
    assert not needs_rehash(stored)


def test_legacy_demo_password_still_works_and_needs_rehash():
    assert verify_password("x", "demo:x")
    assert needs_rehash("demo:x")


def test_chain_node_status():
    node = ChainNode(network=ChainNode.NETWORK_TESTNET)
    node.demo.register_agent("a1")
    st = node.status_dict()
    assert st["network"] == ChainNode.NETWORK_TESTNET
    assert st["agents"] == 1
    assert st["block_height"] >= 1


def test_keystore_revocation():
    store = KeyStore()
    key = store.issue_agent_key("agent-a", owner_id="owner_1")
    store.lookup(key.token)
    store.revoke(key.token)
    with pytest.raises(Exception):
        store.lookup(key.token)


def _testnet_app() -> TestClient:
    settings = Settings(
        env="testnet",
        network_name="syntrends-testnet-1",
        faucet_enabled=True,
        faucet_cooldown_seconds=1.0,
        allow_demo_kyc_approve=True,
        require_real_kyc_on_testnet=False,
    )
    app = create_app(require_owner_kyc=True, mount_web=True, settings=settings)
    return TestClient(app)


def _owner_with_key(client: TestClient) -> tuple[str, str]:
    reg = client.post("/owners/api/register", json={"email": "tn@test.example", "password": "password123"})
    token = reg.json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/owners/api/agreements/accept", headers=headers)
    client.post("/owners/api/syntrendrules/accept", headers=headers, json={"attestation": "I agree."})
    client.post("/owners/api/seeprules/accept", headers=headers, json={"attestation": "I agree."})
    client.post(
        "/owners/api/kyc/submit",
        headers=headers,
        json={"full_name": "Test", "country": "US", "attestation": True},
    )
    owner_id = client.get("/owners/api/me", headers=headers).json()["owner_id"]
    client.post("/owners/api/kyc/approve", json={"owner_id": owner_id})
    conn = client.post(
        "/owners/api/agents/connect",
        headers=headers,
        json={"agent_id": "agent-testnet-1"},
    )
    api_key = conn.json()["api_key"]
    return token, api_key


def test_status_endpoint():
    with _testnet_app() as client:
        data = client.get("/status").json()
        assert data["env"] == "testnet"
        assert data["network"] == "syntrends-testnet-1"
        assert "block_height" in data
        assert data["faucet_enabled"] is True


def test_demo_keys_blocked_on_testnet():
    with _testnet_app() as client:
        assert client.get("/demo/keys").status_code == 404


def test_faucet_credits_agent_and_respects_cooldown():
    with _testnet_app() as client:
        _, api_key = _owner_with_key(client)
        headers = {"Authorization": f"Bearer {api_key}"}
        r1 = client.post("/testnet/faucet", headers=headers)
        assert r1.status_code == 200
        assert "ST/" in r1.text or "STP" in r1.text or "FIAT" in r1.text
        r2 = client.post("/testnet/faucet", headers=headers)
        assert r2.status_code == 400
        assert "cooldown" in r2.json()["detail"].lower()


def test_agent_deposit_forbidden_on_testnet():
    with _testnet_app() as client:
        _, api_key = _owner_with_key(client)
        resp = client.post(
            "/agent/deposit",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"agent_id": "agent-testnet-1", "amount": 50.0},
        )
        assert resp.status_code == 403
        assert "sandbox" in resp.json()["detail"].lower()


def test_faucet_disabled_on_production_even_if_flag_set():
    settings = Settings(
        env="production",
        faucet_enabled=True,
        allow_sandbox_deposit=True,
        require_real_kyc_on_testnet=False,
    )
    app = create_app(require_owner_kyc=True, mount_web=True, settings=settings)
    with TestClient(app) as client:
        info = client.get("/testnet/faucet").json()
        assert info["enabled"] is False
        assert client.get("/status").json()["faucet_enabled"] is False


def test_faucet_info_public():
    with _testnet_app() as client:
        info = client.get("/testnet/faucet").json()
        assert info["enabled"] is True
        assert info["amount"] == 5000.0


def test_owner_can_revoke_key():
    with _testnet_app() as client:
        owner_token, api_key = _owner_with_key(client)
        headers = {"Authorization": f"Bearer {owner_token}"}
        keys_before = client.get("/owners/api/keys", headers=headers).json()["keys"]
        assert len(keys_before) >= 1
        revoke = client.post("/owners/api/keys/revoke", headers=headers, json={"api_key": api_key})
        assert revoke.status_code == 200
        assert client.get("/snapshot", headers={"Authorization": f"Bearer {api_key}"}).status_code == 401


def test_seed_testnet_produces_blocks():
    settings = Settings(env="testnet")
    svc = SynTrendsAPIService(clock=ManualClock(), settings=settings)
    stats = svc.seed_testnet()
    assert stats["blocks"] >= 2
    assert stats["agent_key"] == ""


def test_status_page_served():
    with _testnet_app() as client:
        resp = client.get("/status/")
        assert resp.status_code == 200
        assert "Network Status" in resp.text


def test_passwords_use_scrypt_on_register():
    from api.owners import OwnerRegistry

    reg = OwnerRegistry()
    owner = reg.register("z@test.example", "password123")
    assert owner.password_hash.startswith("scrypt:")
