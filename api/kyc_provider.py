"""Pluggable KYC/AML provider abstraction (Phase F — real identity verification).

The demo ships with `DemoKYCProvider` (an admin "approve" button — fine for
local/staging trust-building, never for a public production environment).
`PersonaKYCProvider` is a real integration point: it creates a hosted
verification session via Persona's Inquiry API and verifies webhook
callbacks with HMAC signature checking, so connecting a real Persona
account is a matter of setting environment variables, not writing code.

Swap in a different vendor (Alloy, Stripe Identity, Onfido, ...) by adding
another `KYCProvider` subclass and registering it in `create_kyc_provider`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal, Mapping
from urllib.parse import urlencode

import httpx

from .config import Settings

KYCDecision = Literal["approved", "declined", "needs_review", "pending"]


class KYCProviderError(Exception):
    pass


class WebhookVerificationError(KYCProviderError):
    """Raised when a webhook signature fails verification — treat as untrusted input."""


@dataclass(frozen=True)
class KYCStartResult:
    """What the owner portal frontend needs to continue verification."""

    mode: Literal["demo", "redirect"]
    provider: str
    redirect_url: str | None = None
    inquiry_id: str | None = None
    instructions: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "provider": self.provider,
            "redirect_url": self.redirect_url,
            "inquiry_id": self.inquiry_id,
            "instructions": self.instructions,
        }


@dataclass(frozen=True)
class KYCWebhookEvent:
    """Normalized result of a provider webhook, regardless of vendor payload shape."""

    owner_id: str
    decision: KYCDecision
    inquiry_id: str | None
    raw_event_name: str


class KYCProvider(ABC):
    name: str

    @abstractmethod
    def start(self, owner_id: str, full_name: str, email: str) -> KYCStartResult:
        """Begin (or resume) identity verification for one owner."""

    def verify_webhook(self, headers: Mapping[str, str], raw_body: bytes) -> KYCWebhookEvent:
        raise KYCProviderError(f"{self.name} provider does not support webhooks")

    @property
    def supports_webhook(self) -> bool:
        return False


class DemoKYCProvider(KYCProvider):
    """Manual admin-approve flow — demo/staging only. Never wire this up
    behind a publicly reachable production environment; `owner_routes.py`
    refuses the admin-approve endpoint whenever `settings.is_production`."""

    name = "demo"

    def start(self, owner_id: str, full_name: str, email: str) -> KYCStartResult:
        return KYCStartResult(
            mode="demo",
            provider=self.name,
            instructions=(
                "Demo mode: an admin approves KYC via POST /owners/api/kyc/approve "
                "(or the 'Approve KYC (demo admin)' button in the owner portal). "
                "This is disabled automatically when SYNTRENDS_ENV=production."
            ),
        )


class PersonaKYCProvider(KYCProvider):
    """Real integration with Persona's Hosted Flow + Inquiry webhooks.

    Docs: https://docs.withpersona.com/docs/hosted-flow
          https://docs.withpersona.com/docs/webhooks

    Webhook signature scheme (`Persona-Signature: t=<unix_ts>,v1=<hex_hmac>`)
    matches Persona's documented format as of the 2023-01-05 API version;
    the inquiry status field paths below may need adjusting if you're on a
    newer API version — verify against your Persona dashboard's webhook
    payload inspector before going live.
    """

    name = "persona"
    HOSTED_FLOW_BASE = "https://withpersona.com/verify"
    API_BASE = "https://api.withpersona.com/api/v1"

    def __init__(
        self,
        *,
        template_id: str,
        api_key: str,
        webhook_secret: str | None,
        environment: str = "sandbox",
        http_client: httpx.Client | None = None,
    ) -> None:
        if not template_id:
            raise KYCProviderError("PERSONA_TEMPLATE_ID is required for the persona provider")
        if not api_key:
            raise KYCProviderError("PERSONA_API_KEY is required for the persona provider")
        self.template_id = template_id
        self.api_key = api_key
        self.webhook_secret = webhook_secret
        self.environment = environment
        self._client = http_client

    @property
    def supports_webhook(self) -> bool:
        return True

    def start(self, owner_id: str, full_name: str, email: str) -> KYCStartResult:
        """Build a Hosted Flow redirect URL. No API call is required to
        start Persona's hosted flow — the inquiry is created client-side
        when the owner lands on the verify page, referencing `owner_id`
        so the webhook can be matched back to our records."""
        params = {
            "inquiry-template-id": self.template_id,
            "reference-id": owner_id,
            "environment": self.environment,
            "fields[name-first]": full_name.split(" ", 1)[0] if full_name else "",
            "fields[name-last]": full_name.split(" ", 1)[1] if " " in full_name else "",
            "fields[email-address]": email,
        }
        redirect_url = f"{self.HOSTED_FLOW_BASE}?{urlencode(params)}"
        return KYCStartResult(mode="redirect", provider=self.name, redirect_url=redirect_url)

    def _verify_signature(self, headers: Mapping[str, str], raw_body: bytes) -> None:
        if not self.webhook_secret:
            raise WebhookVerificationError("PERSONA_WEBHOOK_SECRET is not configured")
        signature_header = headers.get("persona-signature") or headers.get("Persona-Signature")
        if not signature_header:
            raise WebhookVerificationError("missing Persona-Signature header")

        parts: dict[str, str] = {}
        for chunk in signature_header.split(","):
            if "=" not in chunk:
                continue
            k, v = chunk.split("=", 1)
            parts[k.strip()] = v.strip()

        timestamp = parts.get("t")
        provided_sig = parts.get("v1")
        if not timestamp or not provided_sig:
            raise WebhookVerificationError("malformed Persona-Signature header")

        # Reject stale webhooks (replay protection) — 5 minute tolerance.
        try:
            if abs(time.time() - int(timestamp)) > 300:
                raise WebhookVerificationError("webhook timestamp outside tolerance window")
        except ValueError as exc:
            raise WebhookVerificationError("invalid timestamp in Persona-Signature") from exc

        signed_payload = f"{timestamp}.{raw_body.decode('utf-8')}"
        expected_sig = hmac.new(
            self.webhook_secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, provided_sig):
            raise WebhookVerificationError("signature mismatch")

    def verify_webhook(self, headers: Mapping[str, str], raw_body: bytes) -> KYCWebhookEvent:
        self._verify_signature(headers, raw_body)
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise WebhookVerificationError("webhook body is not valid JSON") from exc

        event_name = body.get("data", {}).get("attributes", {}).get("name", "")
        inquiry = body.get("data", {}).get("attributes", {}).get("payload", {}).get("data", {})
        inquiry_attrs = inquiry.get("attributes", {})
        owner_id = inquiry_attrs.get("reference-id") or ""
        inquiry_id = inquiry.get("id")
        status = inquiry_attrs.get("status", "")

        decision: KYCDecision
        name_l = (event_name or "").lower()
        status_l = (status or "").lower().replace("_", "-")
        if "declined" in name_l or "failed" in name_l or status_l in ("declined", "failed"):
            decision = "declined"
        elif "needs-review" in name_l or "needs_review" in name_l or status_l in (
            "needs-review",
            "needs_review",
        ):
            decision = "needs_review"
        elif (
            "approved" in name_l
            or status_l == "approved"
            # Sandbox "Pass verifications" often fires inquiry.completed, not inquiry.approved.
            or name_l == "inquiry.completed"
            or status_l == "completed"
        ):
            decision = "approved"
        else:
            decision = "pending"

        if not owner_id:
            raise WebhookVerificationError("webhook payload missing reference-id (owner_id)")

        return KYCWebhookEvent(
            owner_id=owner_id, decision=decision, inquiry_id=inquiry_id, raw_event_name=event_name
        )

    def fetch_decision_for_owner(self, owner_id: str) -> KYCDecision | None:
        """Pull latest inquiry for this owner from Persona's API (Refresh status).

        Sandbox often never emits inquiry.approved — only inquiry.completed.
        """
        if not owner_id:
            return None
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Key-Inflection": "kebab",
            "Accept": "application/json",
        }
        client = self._client or httpx.Client(timeout=20.0)
        close = self._client is None

        def _rows(params: dict) -> list:
            resp = client.get(f"{self.API_BASE}/inquiries", params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json().get("data") or []
            return data if isinstance(data, list) else []

        def _ref(attrs: dict) -> str:
            return str(attrs.get("reference-id") or attrs.get("reference_id") or "")

        def _status(attrs: dict) -> str:
            return str(attrs.get("status") or "").lower().replace("_", "-")

        def _pick(rows: list) -> KYCDecision | None:
            best: KYCDecision | None = None
            for row in rows:
                if not isinstance(row, dict):
                    continue
                attrs = row.get("attributes") or {}
                if _ref(attrs) and _ref(attrs) != owner_id:
                    continue
                status = _status(attrs)
                if status in ("declined", "failed"):
                    return "declined"
                if status in ("approved", "completed"):
                    best = "approved"
                elif status in ("needs-review", "needs_review") and best is None:
                    best = "needs_review"
            return best

        try:
            rows = _rows({"filter[reference-id]": owner_id, "page[size]": 25})
            decision = _pick(rows)
            if decision is None:
                rows = _rows({"page[size]": 50})
                # Unfiltered list: only match this owner.
                matched = []
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    attrs = row.get("attributes") or {}
                    if _ref(attrs) == owner_id:
                        matched.append(row)
                decision = _pick(matched if matched else [])
            if decision is None:
                raise KYCProviderError(
                    f"Persona found no completed inquiry for {owner_id}. "
                    "Hard-refresh the portal (Ctrl+Shift+R), then Refresh status again."
                )
            return decision
        except KYCProviderError:
            raise
        except Exception as exc:
            raise KYCProviderError(f"Persona inquiry lookup failed: {exc}") from exc
        finally:
            if close:
                client.close()


def create_kyc_provider(settings: Settings) -> KYCProvider:
    """Factory: choose the KYC provider from `Settings`.

    Fails loudly in production (and public testnet when
    ``REQUIRE_REAL_KYC_ON_TESTNET=1``) if a real provider is requested but
    misconfigured — never silently fall back to demo admin-approve there.
    """
    hard_fail = settings.is_production or (
        settings.is_testnet and settings.require_real_kyc_on_testnet and settings.kyc_provider == "persona"
    )

    if settings.kyc_provider == "persona":
        try:
            return PersonaKYCProvider(
                template_id=settings.persona_template_id or "",
                api_key=settings.persona_api_key or "",
                webhook_secret=settings.persona_webhook_secret,
                environment=settings.persona_environment,
            )
        except KYCProviderError:
            if hard_fail:
                raise
            # Local/dev: fall back to demo so work continues without vendor creds.
            return DemoKYCProvider()

    if settings.kyc_provider != "demo" and hard_fail:
        raise KYCProviderError(
            f"unknown KYC_PROVIDER={settings.kyc_provider!r} in {settings.env}; refusing to start "
            "with an unverified identity provider"
        )

    return DemoKYCProvider()
