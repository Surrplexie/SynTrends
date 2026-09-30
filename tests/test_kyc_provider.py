"""Tests for the pluggable KYC provider abstraction (Phase F)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from api.app_factory import create_app
from api.config import Settings
from api.kyc_provider import (
    DemoKYCProvider,
    KYCProviderError,
    PersonaKYCProvider,
    WebhookVerificationError,
    create_kyc_provider,
)


def test_demo_provider_is_default():
    provider = create_kyc_provider(Settings())
    assert isinstance(provider, DemoKYCProvider)
    result = provider.start("owner_1", "Jane Doe", "jane@example.com")
    assert result.mode == "demo"


def test_persona_provider_selected_with_credentials():
    settings = Settings(
        kyc_provider="persona",
        persona_api_key="key_123",
        persona_template_id="itmpl_abc",
        persona_webhook_secret="whsec_test",
    )
    provider = create_kyc_provider(settings)
    assert isinstance(provider, PersonaKYCProvider)
    result = provider.start("owner_1", "Jane Doe", "jane@example.com")
    assert result.mode == "redirect"
    assert result.redirect_url is not None
    assert "inquiry-template-id=itmpl_abc" in result.redirect_url
    assert "reference-id=owner_1" in result.redirect_url


def test_persona_provider_falls_back_to_demo_without_credentials_outside_production():
    settings = Settings(kyc_provider="persona", env="development")
    provider = create_kyc_provider(settings)
    assert isinstance(provider, DemoKYCProvider)


def test_persona_provider_missing_credentials_raises_in_production():
    settings = Settings(kyc_provider="persona", env="production")
    with pytest.raises(KYCProviderError):
        create_kyc_provider(settings)


def test_unknown_provider_raises_in_production():
    settings = Settings(kyc_provider="totally-made-up", env="production")
    with pytest.raises(KYCProviderError):
        create_kyc_provider(settings)


def test_unknown_provider_falls_back_to_demo_outside_production():
    settings = Settings(kyc_provider="totally-made-up", env="development")
    provider = create_kyc_provider(settings)
    assert isinstance(provider, DemoKYCProvider)


def _sign(secret: str, body: bytes, ts: int | None = None) -> str:
    ts = ts if ts is not None else int(time.time())
    signed_payload = f"{ts}.{body.decode('utf-8')}"
    sig = hmac.new(secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _persona_provider(secret: str = "whsec_test") -> PersonaKYCProvider:
    return PersonaKYCProvider(
        template_id="itmpl_abc", api_key="key_123", webhook_secret=secret, environment="sandbox"
    )


def _approved_payload(owner_id: str) -> bytes:
    return json.dumps({
        "data": {
            "attributes": {
                "name": "inquiry.approved",
                "payload": {
                    "data": {
                        "type": "inquiry",
                        "id": "inq_123",
                        "attributes": {"status": "approved", "reference-id": owner_id},
                    }
                },
            }
        }
    }).encode("utf-8")


def test_webhook_signature_verification_accepts_valid_signature():
    provider = _persona_provider()
    body = _approved_payload("owner_42")
    headers = {"persona-signature": _sign("whsec_test", body)}
    event = provider.verify_webhook(headers, body)
    assert event.owner_id == "owner_42"
    assert event.decision == "approved"
    assert event.inquiry_id == "inq_123"


def test_webhook_signature_verification_rejects_bad_signature():
    provider = _persona_provider()
    body = _approved_payload("owner_42")
    headers = {"persona-signature": _sign("wrong-secret", body)}
    with pytest.raises(WebhookVerificationError):
        provider.verify_webhook(headers, body)


def test_webhook_signature_verification_rejects_missing_header():
    provider = _persona_provider()
    body = _approved_payload("owner_42")
    with pytest.raises(WebhookVerificationError):
        provider.verify_webhook({}, body)


def test_webhook_signature_verification_rejects_stale_timestamp():
    provider = _persona_provider()
    body = _approved_payload("owner_42")
    stale_ts = int(time.time()) - 10_000
    headers = {"persona-signature": _sign("whsec_test", body, ts=stale_ts)}
    with pytest.raises(WebhookVerificationError):
        provider.verify_webhook(headers, body)


def test_webhook_declined_event_maps_to_declined_decision():
    provider = _persona_provider()
    body = json.dumps({
        "data": {
            "attributes": {
                "name": "inquiry.declined",
                "payload": {
                    "data": {
                        "id": "inq_999",
                        "attributes": {"status": "declined", "reference-id": "owner_9"},
                    }
                },
            }
        }
    }).encode("utf-8")
    headers = {"persona-signature": _sign("whsec_test", body)}
    event = provider.verify_webhook(headers, body)
    assert event.decision == "declined"


def test_webhook_inquiry_completed_sandbox_maps_to_approved():
    provider = _persona_provider()
    body = json.dumps({
        "data": {
            "attributes": {
                "name": "inquiry.completed",
                "payload": {
                    "data": {
                        "id": "inq_sandbox",
                        "attributes": {"status": "completed", "reference-id": "owner_42"},
                    }
                },
            }
        }
    }).encode("utf-8")
    headers = {"persona-signature": _sign("whsec_test", body)}
    event = provider.verify_webhook(headers, body)
    assert event.decision == "approved"


def test_fetch_decision_for_owner_treats_completed_as_approved():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "reference-id" in str(request.url)
        return httpx.Response(
            200,
            json={"data": [{"type": "inquiry", "id": "inq_1", "attributes": {"status": "completed"}}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = PersonaKYCProvider(
        template_id="itmpl_abc",
        api_key="key_123",
        webhook_secret="whsec_test",
        environment="sandbox",
        http_client=client,
    )
    assert provider.fetch_decision_for_owner("owner_42") == "approved"


def test_demo_provider_does_not_support_webhook():
    provider = DemoKYCProvider()
    assert provider.supports_webhook is False


# -- integration: owner_routes gating -----------------------------------------


def _register_owner(client: TestClient) -> tuple[str, dict[str, str]]:
    reg = client.post("/owners/api/register", json={"email": "kyc@test.example", "password": "password123"})
    token = reg.json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/owners/api/agreements/accept", headers=headers)
    client.post("/owners/api/syntrendrules/accept", headers=headers, json={"attestation": "I agree."})
    client.post("/owners/api/seeprules/accept", headers=headers, json={"attestation": "I agree."})
    return reg.json()["owner"]["owner_id"], headers


def test_config_endpoint_reports_demo_provider():
    app = create_app(require_owner_kyc=True, mount_web=True, settings=Settings(kyc_provider="demo"))
    with TestClient(app) as client:
        data = client.get("/owners/api/config").json()
        assert data["kyc_provider"] == "demo"
        assert data["demo_admin_approve_enabled"] is True
        assert data.get("public_beta") is False


def test_demo_approve_disabled_on_public_testnet():
    """Phase K — public testnet never exposes demo admin KYC approve."""
    settings = Settings(env="testnet", kyc_provider="demo", allow_demo_kyc_approve=False)
    app = create_app(require_owner_kyc=True, mount_web=True, settings=settings)
    with TestClient(app) as client:
        cfg = client.get("/owners/api/config").json()
        assert cfg["demo_admin_approve_enabled"] is False
        assert cfg["public_beta"] is True
        assert cfg["testnet"] is True

        owner_id, headers = _register_owner(client)
        client.post(
            "/owners/api/kyc/submit",
            headers=headers,
            json={"full_name": "Test Owner", "country": "US", "attestation": True},
        )
        resp = client.post("/owners/api/kyc/approve", json={"owner_id": owner_id})
        assert resp.status_code == 403


def test_demo_approve_allowed_on_local_testnet_ship_flag():
    settings = Settings(env="testnet", kyc_provider="demo", allow_demo_kyc_approve=True)
    app = create_app(require_owner_kyc=True, mount_web=True, settings=settings)
    with TestClient(app) as client:
        cfg = client.get("/owners/api/config").json()
        assert cfg["demo_admin_approve_enabled"] is True
        assert cfg["public_beta"] is False


def test_persona_hard_fails_on_testnet_without_credentials():
    settings = Settings(
        env="testnet",
        kyc_provider="persona",
        require_real_kyc_on_testnet=True,
    )
    with pytest.raises(KYCProviderError):
        create_kyc_provider(settings)


def test_demo_approve_disabled_in_production_settings():
    settings = Settings(env="production", kyc_provider="demo")
    app = create_app(require_owner_kyc=True, mount_web=True, settings=settings)
    with TestClient(app) as client:
        owner_id, headers = _register_owner(client)
        client.post(
            "/owners/api/kyc/submit",
            headers=headers,
            json={"full_name": "Test Owner", "country": "US", "attestation": True},
        )
        resp = client.post("/owners/api/kyc/approve", json={"owner_id": owner_id})
        assert resp.status_code == 403


def test_kyc_start_with_persona_returns_redirect_and_records_inquiry():
    settings = Settings(
        kyc_provider="persona",
        persona_api_key="key_123",
        persona_template_id="itmpl_abc",
        persona_webhook_secret="whsec_test",
    )
    app = create_app(require_owner_kyc=True, mount_web=True, settings=settings)
    with TestClient(app) as client:
        owner_id, headers = _register_owner(client)
        resp = client.post("/owners/api/kyc/start", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "redirect"
        assert "withpersona.com" in data["redirect_url"]

        me = client.get("/owners/api/me", headers=headers).json()
        assert me["kyc_status"] == "submitted"
        assert me["kyc_provider"] == "persona"

        # demo-approve must be refused once a real provider is configured
        approve = client.post("/owners/api/kyc/approve", json={"owner_id": owner_id})
        assert approve.status_code == 403


def test_kyc_webhook_approves_owner_end_to_end():
    settings = Settings(
        kyc_provider="persona",
        persona_api_key="key_123",
        persona_template_id="itmpl_abc",
        persona_webhook_secret="whsec_test",
    )
    app = create_app(require_owner_kyc=True, mount_web=True, settings=settings)
    with TestClient(app) as client:
        owner_id, headers = _register_owner(client)
        client.post("/owners/api/kyc/start", headers=headers)

        body = _approved_payload(owner_id)
        sig = _sign("whsec_test", body)
        resp = client.post(
            "/owners/api/kyc/webhook",
            content=body,
            headers={"Content-Type": "application/json", "persona-signature": sig},
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "approved"

        me = client.get("/owners/api/me", headers=headers).json()
        assert me["kyc_status"] == "approved"
        assert me["can_connect_agent"] is True


def test_kyc_webhook_rejects_bad_signature_end_to_end():
    settings = Settings(
        kyc_provider="persona",
        persona_api_key="key_123",
        persona_template_id="itmpl_abc",
        persona_webhook_secret="whsec_test",
    )
    app = create_app(require_owner_kyc=True, mount_web=True, settings=settings)
    with TestClient(app) as client:
        owner_id, headers = _register_owner(client)
        client.post("/owners/api/kyc/start", headers=headers)

        body = _approved_payload(owner_id)
        resp = client.post(
            "/owners/api/kyc/webhook",
            content=body,
            headers={"Content-Type": "application/json", "persona-signature": "t=1,v1=bogus"},
        )
        assert resp.status_code == 401


def test_kyc_webhook_404_when_provider_does_not_support_it():
    app = create_app(require_owner_kyc=True, mount_web=True, settings=Settings(kyc_provider="demo"))
    with TestClient(app) as client:
        resp = client.post("/owners/api/kyc/webhook", content=b"{}")
        assert resp.status_code == 404
