"""3rdPS keys: free to issue, calendar expiry, bill Curation Tokens."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from api.auth import APIKey, KeyKind, KeyStore
from api.main import app


def test_unused_thirdps_key_owes_zero():
    with TestClient(app) as client:
        issued = client.post("/keys/thirdps", json={"label": "shelf"}).json()
        assert issued["issuance_fee"] == 0
        assert issued["billing_model"] == "curation_tokens"
        assert issued["usage_weight"] == 0
        assert issued["amount_due"] == 0
        assert issued["api_key"].startswith("st_thirdps_")
        assert issued["expires_at"] > time.time()

        bill = client.get(
            "/thirdps/billing",
            headers={"Authorization": f"Bearer {issued['api_key']}"},
        ).json()
        assert bill["issuance_fee"] == 0
        assert bill["raw_ct"] == 0
        assert bill["amount_due"] == 0
        assert bill["unit"] == "CT"


def test_thirdps_ct_grows_with_snapshot_use():
    with TestClient(app) as client:
        token = client.post("/keys/thirdps", json={"label": "hot"}).json()["api_key"]
        headers = {"Authorization": f"Bearer {token}"}
        snap = client.get("/snapshot", headers=headers)
        assert snap.status_code == 200
        bill = client.get("/thirdps/billing", headers=headers).json()
        assert bill["raw_ct"] > 0
        assert bill["amount_due"] > 0
        assert set(bill["product_classes"]) == {"market", "seepnews"}
        assert bill["bundle_multiplier"] == 16
        unused = client.post("/keys/thirdps", json={"label": "never"}).json()
        never = client.get(
            "/thirdps/billing",
            headers={"Authorization": f"Bearer {unused['api_key']}"},
        ).json()
        assert never["amount_due"] == 0
        assert never["raw_ct"] == 0
        assert bill["amount_due"] > never["amount_due"]


def test_specialist_cheaper_than_kitchen_sink():
    with TestClient(app) as client:
        hud = client.post("/keys/thirdps", json={"label": "hud"}).json()["api_key"]
        mix = client.post("/keys/thirdps", json={"label": "mix"}).json()["api_key"]
        h_hud = {"Authorization": f"Bearer {hud}"}
        h_mix = {"Authorization": f"Bearer {mix}"}
        assert client.get("/stream/market", headers=h_hud, params={"live": 0}).status_code == 200
        assert client.get("/snapshot", headers=h_mix).status_code == 200
        hud_bill = client.get("/thirdps/billing", headers=h_hud).json()
        mix_bill = client.get("/thirdps/billing", headers=h_mix).json()
        assert hud_bill["bundle_multiplier"] == 1
        assert mix_bill["bundle_multiplier"] == 16
        assert mix_bill["invoice_ct"] > hud_bill["invoice_ct"]


def test_quote_805_seepnews_is_322():
    with TestClient(app) as client:
        q = client.get("/thirdps/quote", params={"agents": 805}).json()
        assert q["per_pull"]["seepnews"] == 3.22
        assert q["per_pull"]["chain_explorer"] == 0
        assert q["not_a_coin"] is True


def test_explorer_is_free():
    from api.web_app import app as web_app

    with TestClient(web_app) as client:
        assert client.get("/explorer/api/summary").status_code == 200


def test_expired_thirdps_key_rejected():
    store = KeyStore()
    key = store.issue_thirdps_key("old", ttl_seconds=1)
    key.expires_at = time.time() - 10
    store.register(key)
    try:
        store.lookup(key.token)
        assert False, "expired key should not lookup"
    except Exception as exc:
        assert "expired" in str(exc).lower()


def test_well_known_thirdps_ct_billing():
    with TestClient(app) as client:
        life = client.get("/.well-known/syntrends").json()["key_lifecycle"]["thirdps_api"]
        assert life["expires"] is True
        assert life["issuance_fee"] == 0
        assert "Curation Tokens" in life["billing"]
        assert client.get("/.well-known/syntrends").json()["apis"]["thirdps_api"]["issuance_fee"] == 0
        assert client.get("/.well-known/syntrends").json()["apis"]["thirdps_api"]["unit"] == "CT"


def test_invoice_amount_helper():
    key = APIKey(token="x", kind=KeyKind.THIRDPSS, usage_weight=0)
    assert key.invoice_amount(0.001) == 0
    key.usage_weight = 10
    assert key.invoice_amount(0.001) == 0.01
