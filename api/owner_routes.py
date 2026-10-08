"""Owner portal JSON API — KYC, agreements, agent connection (Phase D/F)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from .auth import AuthError
from .agent_routes import get_owner_session, get_service
from .kyc_provider import KYCProviderError, WebhookVerificationError
from .owner_cash import OwnerCashError
from .owners import AGREEMENTS_VERSION, KYCError, KYCStatus, OwnerAuthError, OwnerError
from .tax import render_tax_csv
from .syntrendrules import SYNTRENDRULES_VERSION, SyntrendrulesError

router = APIRouter(prefix="/owners/api", tags=["owners"])


class RegisterBody(BaseModel):
    email: str
    password: str = Field(min_length=8)


class LoginBody(BaseModel):
    email: str
    password: str


class KYCSubmitBody(BaseModel):
    full_name: str
    country: str
    attestation: bool = False


class ConnectAgentBody(BaseModel):
    agent_id: str
    label: str | None = None


class AgentControlBody(BaseModel):
    agent_id: str


class AgentResumeBody(BaseModel):
    agent_id: str
    gradual_seconds: float = Field(
        default=0,
        ge=0,
        le=300,
        description="Optional cooldown before writes resume (demo gradual restart)",
    )


class SeeprulesAcceptBody(BaseModel):
    attestation: str = Field(description='Must be exactly "I agree." per docs/seeprules.md')


class SyntrendrulesAcceptBody(BaseModel):
    attestation: str = Field(description='Must be exactly "I agree." per docs/syntrendrules.md')


class AdminApproveBody(BaseModel):
    owner_id: str


class OwnerCashCreditBody(BaseModel):
    amount: float | None = Field(default=None, gt=0)


class OwnerCashMoveBody(BaseModel):
    agent_id: str
    amount: float = Field(gt=0)


@router.post("/register")
def register(body: RegisterBody):
    svc = get_service()
    try:
        owner = svc.owners.register(body.email, body.password)
        session = svc.owners.login(body.email, body.password)
    except OwnerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    svc.persist()
    return {
        "session_token": session.token,
        "owner": svc.owners.public_view(owner),
    }


@router.post("/login")
def login(body: LoginBody):
    svc = get_service()
    try:
        session = svc.owners.login(body.email, body.password)
        owner = svc.owners.lookup_session(session.token)
    except OwnerAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {
        "session_token": session.token,
        "owner": svc.owners.public_view(owner),
    }


@router.get("/me")
def me(authorization: Annotated[str | None, Header()] = None):
    owner = get_owner_session(authorization)
    svc = get_service()
    view = svc.owners.public_view(owner)
    view["agents"] = svc.agent_pause_status_for_owner(owner)
    return view


@router.post("/agreements/accept")
def accept_agreements(authorization: Annotated[str | None, Header()] = None):
    owner = get_owner_session(authorization)
    svc = get_service()
    updated = svc.owners.accept_agreements(owner.owner_id, AGREEMENTS_VERSION)
    svc.persist()
    return svc.owners.public_view(updated)


@router.get("/config")
def portal_config():
    """Tells the owner portal frontend which KYC flow to render — real
    provider redirect vs. the demo admin-approve button (never both)."""
    svc = get_service()
    demo_approve = svc.settings.demo_kyc_approve_allowed and svc.kyc.name == "demo"
    return {
        "env": svc.settings.env,
        "network": svc.settings.network_name,
        "kyc_provider": svc.kyc.name,
        "demo_admin_approve_enabled": demo_approve,
        "faucet_enabled": svc.settings.faucet_allowed,
        "owner_cash_credit_enabled": svc.owner_simulated_credit_allowed(),
        "cash_unit": "SYNTRENDS",
        "testnet": svc.settings.is_testnet,
        "public_beta": svc.settings.is_testnet and not demo_approve,
    }


@router.post("/kyc/submit")
def submit_kyc(body: KYCSubmitBody, authorization: Annotated[str | None, Header()] = None):
    owner = get_owner_session(authorization)
    svc = get_service()
    try:
        updated = svc.owners.submit_kyc(owner.owner_id, body.full_name, body.country, body.attestation)
    except KYCError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    svc.persist()
    return svc.owners.public_view(updated)


@router.post("/kyc/start")
def start_kyc(authorization: Annotated[str | None, Header()] = None):
    """Begin verification with the configured provider. Demo mode returns
    instructions for the admin-approve shortcut; a real provider (e.g.
    Persona) returns a hosted-flow redirect URL."""
    owner = get_owner_session(authorization)
    svc = get_service()
    try:
        result = svc.kyc.start(owner.owner_id, owner.kyc_full_name or owner.email, owner.email)
    except KYCProviderError as exc:
        raise HTTPException(status_code=502, detail=f"KYC provider error: {exc}") from exc
    svc.owners.set_kyc_inquiry(owner.owner_id, svc.kyc.name, result.inquiry_id)
    svc.persist()
    return result.to_dict()


@router.post("/kyc/refresh")
def refresh_kyc(authorization: Annotated[str | None, Header()] = None):
    """Re-read KYC from the provider (Persona Inquiry API). Use after hosted
    flow when the webhook never sent inquiry.approved (sandbox completed)."""
    owner = get_owner_session(authorization)
    svc = get_service()
    if owner.kyc_status == KYCStatus.APPROVED:
        return svc.owners.public_view(owner)
    fetch = getattr(svc.kyc, "fetch_decision_for_owner", None)
    if not callable(fetch):
        return svc.owners.public_view(svc.owners.get_owner(owner.owner_id))
    try:
        decision = fetch(owner.owner_id)
    except KYCProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    try:
        if decision == "approved":
            svc.owners.approve_kyc(owner.owner_id)
        elif decision == "declined":
            svc.owners.reject_kyc(owner.owner_id)
    except (KYCError, OwnerAuthError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    svc.persist()
    return svc.owners.public_view(svc.owners.get_owner(owner.owner_id))


@router.post("/kyc/approve")
def approve_kyc(body: AdminApproveBody):
    """Demo-only admin shortcut — auto-approves KYC without a compliance
    queue. Allowed only on local demo envs (or ``ALLOW_DEMO_KYC_APPROVE=1``).
    Never on production or public testnet. Real providers approve via webhook.
    """
    svc = get_service()
    if not svc.settings.demo_kyc_approve_allowed:
        raise HTTPException(
            status_code=403,
            detail=(
                "demo KYC approval is disabled on this network — "
                "complete identity verification via the configured KYC provider"
            ),
        )
    if svc.kyc.name != "demo":
        raise HTTPException(
            status_code=403,
            detail=f"KYC provider is {svc.kyc.name!r} — approval must come from its webhook, not this admin shortcut",
        )
    try:
        updated = svc.owners.approve_kyc(body.owner_id)
    except KYCError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    svc.persist()
    return svc.owners.public_view(updated)


@router.post("/kyc/webhook")
async def kyc_webhook(request: Request):
    """Provider callback (e.g. Persona inquiry.approved/declined). Verified
    by HMAC signature, not an owner session — this endpoint is reachable
    without auth headers by design, same as any webhook receiver."""
    svc = get_service()
    if not svc.kyc.supports_webhook:
        raise HTTPException(status_code=404, detail=f"{svc.kyc.name} provider does not use webhooks")

    raw_body = await request.body()
    try:
        event = svc.kyc.verify_webhook(dict(request.headers), raw_body)
    except WebhookVerificationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    try:
        if event.decision == "approved":
            svc.owners.approve_kyc(event.owner_id)
        elif event.decision == "declined":
            svc.owners.reject_kyc(event.owner_id)
    except (KYCError, OwnerAuthError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    svc.persist()
    return {"received": True, "decision": event.decision}


class RevokeKeyBody(BaseModel):
    api_key: str


@router.get("/keys")
def list_keys(authorization: Annotated[str | None, Header()] = None):
    """List active API keys issued to this owner (token prefixes only)."""
    owner = get_owner_session(authorization)
    svc = get_service()
    keys = svc.keys.list_for_owner(owner.owner_id)
    return {
        "keys": [
            {
                "prefix": k.token[:16] + "…",
                "kind": k.kind.value,
                "agent_id": k.agent_id,
                "label": k.label,
                "created_at": k.created_at,
            }
            for k in keys
        ]
    }


@router.post("/keys/revoke")
def revoke_key(body: RevokeKeyBody, authorization: Annotated[str | None, Header()] = None):
    owner = get_owner_session(authorization)
    svc = get_service()
    try:
        svc.revoke_agent_key(owner, body.api_key)
    except AuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"revoked": True}


@router.post("/syntrendrules/accept")
def accept_syntrendrules(body: SyntrendrulesAcceptBody, authorization: Annotated[str | None, Header()] = None):
    """Owner accepts SynTrends platform terms + liability waiver (docs/syntrendrules.md)."""
    owner = get_owner_session(authorization)
    svc = get_service()
    try:
        updated = svc.accept_syntrendrules_owner(owner, body.attestation)
    except SyntrendrulesError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return svc.owners.public_view(updated)


@router.post("/seeprules/accept")
def accept_seeprules(body: SeeprulesAcceptBody, authorization: Annotated[str | None, Header()] = None):
    """Owner accepts Seepnews rules + liability contract (docs/seeprules.md)."""
    owner = get_owner_session(authorization)
    svc = get_service()
    try:
        updated = svc.accept_seeprules_owner(owner, body.attestation)
    except SeeprulesError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return svc.owners.public_view(updated)


@router.get("/cash")
def owner_cash(authorization: Annotated[str | None, Header()] = None):
    """Owner $syntrends chip pool and per-agent allocations."""
    owner = get_owner_session(authorization)
    svc = get_service()
    return svc.owner_cash_view(owner)


@router.post("/cash/credit")
def owner_cash_credit(body: OwnerCashCreditBody, authorization: Annotated[str | None, Header()] = None):
    """Simulated owner chip (testnet/demo). Live networks reject this."""
    owner = get_owner_session(authorization)
    svc = get_service()
    try:
        return svc.owner_cash_credit(owner, body.amount)
    except OwnerCashError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/cash/allocate")
def owner_cash_allocate(body: OwnerCashMoveBody, authorization: Annotated[str | None, Header()] = None):
    """Move owner chip into a connected agent's wallet."""
    owner = get_owner_session(authorization)
    svc = get_service()
    try:
        return svc.owner_cash_allocate(owner, body.agent_id, body.amount)
    except OwnerCashError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except OwnerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cash/recall")
def owner_cash_recall(body: OwnerCashMoveBody, authorization: Annotated[str | None, Header()] = None):
    """Pull unused agent chip back to the owner pool (not AICoins)."""
    owner = get_owner_session(authorization)
    svc = get_service()
    try:
        return svc.owner_cash_recall(owner, body.agent_id, body.amount)
    except OwnerCashError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except OwnerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/agents/connect")
def connect_agent(body: ConnectAgentBody, authorization: Annotated[str | None, Header()] = None):
    """Issue an agent API key after KYC + agreements. Returns the key once."""
    owner = get_owner_session(authorization)
    svc = get_service()
    try:
        api_key = svc.create_agent_key(body.agent_id, body.label or "", owner=owner)
    except KYCError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except OwnerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    svc.persist()
    return {
        "agent_id": body.agent_id,
        "api_key": api_key,
        "api_base_url_hint": "Use the agent API host (e.g. api.syntrends.com), not this owner portal.",
    }


@router.get("/agents/status")
def agents_status(authorization: Annotated[str | None, Header()] = None):
    """Pause/resume state for each agent linked to this owner."""
    owner = get_owner_session(authorization)
    svc = get_service()
    return {"agents": svc.agent_pause_status_for_owner(owner)}


@router.post("/agents/pause")
def pause_agent(body: AgentControlBody, authorization: Annotated[str | None, Header()] = None):
    """Instantly halt agent writes (trades, posts, faucet). Reads continue."""
    owner = get_owner_session(authorization)
    svc = get_service()
    try:
        status = svc.pause_agent(owner, body.agent_id)
    except OwnerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return status


@router.post("/agents/resume")
def resume_agent(body: AgentResumeBody, authorization: Annotated[str | None, Header()] = None):
    """Restore agent writes. Optional ``gradual_seconds`` blocks writes briefly after resume."""
    owner = get_owner_session(authorization)
    svc = get_service()
    try:
        status = svc.resume_agent(owner, body.agent_id, gradual_seconds=body.gradual_seconds)
    except OwnerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return status


@router.get("/tax/export", response_class=PlainTextResponse)
def tax_export(authorization: Annotated[str | None, Header()] = None):
    owner = get_owner_session(authorization)
    svc = get_service()
    if not owner.agent_ids:
        raise HTTPException(status_code=400, detail="no connected agents to export")
    csv_body = render_tax_csv(svc.demo, owner.agent_ids)
    return PlainTextResponse(
        csv_body,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=syntrends_tax_export_demo.csv"},
    )
