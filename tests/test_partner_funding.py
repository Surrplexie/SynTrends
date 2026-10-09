"""Partner inbound funding webhook — HMAC credit to owner pool."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient

from api.app_factory import create_app
from api.config import Settings
from api.web_app import app


def _sign(secret: str, body: bytes, ts: int | None = None) -> dict[str, str]:
    timestamp = str(ts if ts is not None else int(time.time()))
    signed = f"{timestamp}.{body.decode('utf-8')}"
    v1 = hmac.new(secret.encode("utf-8"), signed.encode("utf-8"), hashlib.sha256).hexdigest()
    return {"ST-Partner-Signature": f"t={timestamp},v1={v1}", "Content-Type": "application/json"}


def test_partner_webhook_dark_without_secret():
    with TestClient(app) as client:
        resp = client.post("/owners/api/cash/partner-webhook", content=b"{}")
        assert resp.status_code == 404


def test_partner_webhook_credits_and_is_idempotent():
    secret = "partner_test_secret"
    settings = Settings(
        env="production",
        faucet_enabled=False,
        partner_funding_secret=secret,
        partner_funding_enabled=False,
        allow_demo_kyc_approve=True,
        kyc_provider="demo",
    )
    live = create_app(require_owner_kyc=True, mount_web=True, settings=settings)
    try:
        with TestClient(live) as client:
            cfg = client.get("/owners/api/config").json()
            assert cfg["owner_cash_credit_enabled"] is False
            assert cfg["partner_funding_configured"] is True
            reg = client.post(
                "/owners/api/register",
                json={"email": "partner-fund@test.example", "password": "password123"},
            )
            owner_id = reg.json()["owner"]["owner_id"]
            payload = {
                "event": "funding.credited",
                "external_id": "pay_1",
                "owner_id": owner_id,
                "amount": 25.0,
                "currency": "USD",
            }
            raw = json.dumps(payload).encode("utf-8")
            first = client.post(
                "/owners/api/cash/partner-webhook",
                content=raw,
                headers=_sign(secret, raw),
            )
            assert first.status_code == 200, first.text
            assert first.json()["duplicate"] is False
            assert first.json()["owner_balance"] == 25.0

            second = client.post(
                "/owners/api/cash/partner-webhook",
                content=raw,
                headers=_sign(secret, raw),
            )
            assert second.status_code == 200
            assert second.json()["duplicate"] is True
            assert second.json()["owner_balance"] == 25.0

            tok = {"Authorization": f"Bearer {reg.json()['session_token']}"}
            cash = client.get("/owners/api/cash", headers=tok).json()
            assert cash["owner_balance"] == 25.0
            assert cash["recent"][-1]["kind"] == "partner"

            bad = client.post(
                "/owners/api/cash/partner-webhook",
                content=raw,
                headers={"ST-Partner-Signature": "t=1,v1=dead"},
            )
            assert bad.status_code == 401
    finally:
        create_app(require_owner_kyc=True, mount_web=True)


def test_partner_webhook_off_on_testnet_even_with_secret():
    settings = Settings(
        env="testnet",
        faucet_enabled=True,
        partner_funding_secret="x",
        partner_funding_enabled=False,
    )
    app2 = create_app(require_owner_kyc=True, mount_web=True, settings=settings)
    try:
        with TestClient(app2) as client:
            resp = client.post("/owners/api/cash/partner-webhook", content=b"{}")
            assert resp.status_code == 403
    finally:
        create_app(require_owner_kyc=True, mount_web=True)
