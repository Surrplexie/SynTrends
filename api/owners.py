"""Owner accounts, agreements, and KYC/AML stub for Phase D.

Human owners complete verification on the owner portal before receiving
agent API keys. This module does not expose market, AICoin, or Seepnews
content — only identity and compliance state.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from enum import Enum


from .passwords import hash_password, needs_rehash, verify_password
from .seeprules import SEEPRULES_VERSION
from .syntrendrules import SYNTRENDRULES_VERSION


AGREEMENTS_VERSION = "2026-07-29-demo"


class KYCStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class OwnerError(Exception):
    pass


class OwnerAuthError(OwnerError):
    pass


class KYCError(OwnerError):
    pass


@dataclass
class Owner:
    owner_id: str
    email: str
    password_hash: str  # demo: plaintext prefix "demo:"
    agreements_version: str | None = None
    agreements_accepted_at: float | None = None
    seeprules_version: str | None = None
    seeprules_accepted_at: float | None = None
    syntrendrules_version: str | None = None
    syntrendrules_accepted_at: float | None = None
    kyc_status: KYCStatus = KYCStatus.PENDING
    kyc_full_name: str = ""
    kyc_country: str = ""
    kyc_submitted_at: float | None = None
    kyc_approved_at: float | None = None
    kyc_inquiry_id: str | None = None
    kyc_provider: str | None = None
    agent_ids: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass
class OwnerSession:
    token: str
    owner_id: str
    created_at: float = field(default_factory=time.time)


class OwnerRegistry:
    """In-memory owner store for demo/staging/testnet."""

    def __init__(self, *, session_ttl_seconds: float = 86400.0 * 7) -> None:
        self._owners: dict[str, Owner] = {}
        self._owners_by_email: dict[str, str] = {}
        self._sessions: dict[str, OwnerSession] = {}
        self._session_ttl = session_ttl_seconds
        self._lock = threading.RLock()

    def register(self, email: str, password: str) -> Owner:
        email = email.strip().lower()
        if not email or "@" not in email:
            raise OwnerError("valid email required")
        if len(password) < 8:
            raise OwnerError("password must be at least 8 characters")
        with self._lock:
            if email in self._owners_by_email:
                raise OwnerError("email already registered")
            owner_id = f"owner_{secrets.token_hex(8)}"
            owner = Owner(
                owner_id=owner_id,
                email=email,
                password_hash=hash_password(password),
            )
            self._owners[owner_id] = owner
            self._owners_by_email[email] = owner_id
            return owner

    def login(self, email: str, password: str) -> OwnerSession:
        email = email.strip().lower()
        with self._lock:
            owner_id = self._owners_by_email.get(email)
            if not owner_id:
                raise OwnerAuthError("invalid email or password")
            owner = self._owners[owner_id]
            if not verify_password(password, owner.password_hash):
                raise OwnerAuthError("invalid email or password")
            if needs_rehash(owner.password_hash):
                owner.password_hash = hash_password(password)
            token = f"owner_session_{secrets.token_hex(16)}"
            session = OwnerSession(token=token, owner_id=owner_id)
            self._sessions[token] = session
            return session

    def lookup_session(self, token: str | None) -> Owner:
        if not token:
            raise OwnerAuthError("missing owner session token")
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                raise OwnerAuthError("invalid or expired owner session")
            if time.time() - session.created_at > self._session_ttl:
                del self._sessions[token]
                raise OwnerAuthError("owner session expired — log in again")
            owner = self._owners.get(session.owner_id)
            if owner is None:
                raise OwnerAuthError("owner not found")
            return owner

    def get_owner(self, owner_id: str) -> Owner:
        """Public lookup by ID (no session) — used by provider webhooks,
        which authenticate via signature, not an owner session token."""
        with self._lock:
            return self._require_owner(owner_id)

    def accept_agreements(self, owner_id: str, version: str = AGREEMENTS_VERSION) -> Owner:
        with self._lock:
            owner = self._require_owner(owner_id)
            owner.agreements_version = version
            owner.agreements_accepted_at = time.time()
            return owner

    def accept_syntrendrules(self, owner_id: str, version: str = SYNTRENDRULES_VERSION) -> Owner:
        with self._lock:
            owner = self._require_owner(owner_id)
            owner.syntrendrules_version = version
            owner.syntrendrules_accepted_at = time.time()
            return owner

    def accept_seeprules(self, owner_id: str, version: str = SEEPRULES_VERSION) -> Owner:
        with self._lock:
            owner = self._require_owner(owner_id)
            owner.seeprules_version = version
            owner.seeprules_accepted_at = time.time()
            return owner

    def submit_kyc(self, owner_id: str, full_name: str, country: str, attestation: bool) -> Owner:
        if not attestation:
            raise KYCError("you must attest that the information provided is accurate")
        full_name = full_name.strip()
        country = country.strip()
        if not full_name or not country:
            raise KYCError("full legal name and country of residence are required")
        with self._lock:
            owner = self._require_owner(owner_id)
            if owner.agreements_accepted_at is None:
                raise KYCError("accept the platform agreements before submitting KYC")
            owner.kyc_full_name = full_name
            owner.kyc_country = country
            owner.kyc_status = KYCStatus.SUBMITTED
            owner.kyc_submitted_at = time.time()
            return owner

    def approve_kyc(self, owner_id: str) -> Owner:
        """Demo admin action — production would be a compliance review queue."""
        with self._lock:
            owner = self._require_owner(owner_id)
            if owner.kyc_status not in (KYCStatus.SUBMITTED, KYCStatus.PENDING):
                raise KYCError(f"cannot approve KYC in state {owner.kyc_status.value}")
            owner.kyc_status = KYCStatus.APPROVED
            owner.kyc_approved_at = time.time()
            return owner

    def reject_kyc(self, owner_id: str) -> Owner:
        with self._lock:
            owner = self._require_owner(owner_id)
            owner.kyc_status = KYCStatus.REJECTED
            return owner

    def set_kyc_inquiry(self, owner_id: str, provider: str, inquiry_id: str | None) -> Owner:
        """Record that verification was started with an external provider
        (called from `/kyc/start`) so a later webhook can be matched back
        to this owner via `reference-id` even without an inquiry_id."""
        with self._lock:
            owner = self._require_owner(owner_id)
            owner.kyc_provider = provider
            owner.kyc_inquiry_id = inquiry_id
            if owner.kyc_status == KYCStatus.PENDING:
                owner.kyc_status = KYCStatus.SUBMITTED
                owner.kyc_submitted_at = time.time()
            return owner

    def can_issue_agent_key(self, owner: Owner) -> None:
        if owner.agreements_accepted_at is None:
            raise KYCError("accept the platform agreements first")
        if owner.syntrendrules_accepted_at is None:
            raise KYCError("accept the SynTrends platform terms (syntrendrules) first")
        if owner.seeprules_accepted_at is None:
            raise KYCError("accept the Seepnews rules contract (seeprules) first")
        if owner.kyc_status != KYCStatus.APPROVED:
            raise KYCError("KYC must be approved before connecting an agent")

    def bind_agent(self, owner_id: str, agent_id: str) -> None:
        agent_id = agent_id.strip()
        if not agent_id or " " in agent_id:
            raise OwnerError("agent_id must be a single token without spaces")
        with self._lock:
            owner = self._require_owner(owner_id)
            if agent_id not in owner.agent_ids:
                owner.agent_ids.append(agent_id)

    def public_view(self, owner: Owner) -> dict:
        return {
            "owner_id": owner.owner_id,
            "email": owner.email,
            "agreements_accepted": owner.agreements_accepted_at is not None,
            "agreements_version": owner.agreements_version,
            "seeprules_accepted": owner.seeprules_accepted_at is not None,
            "seeprules_version": owner.seeprules_version,
            "syntrendrules_accepted": owner.syntrendrules_accepted_at is not None,
            "syntrendrules_version": owner.syntrendrules_version,
            "kyc_status": owner.kyc_status.value,
            "kyc_provider": owner.kyc_provider,
            "agent_ids": list(owner.agent_ids),
            "can_connect_agent": (
                owner.agreements_accepted_at is not None
                and owner.syntrendrules_accepted_at is not None
                and owner.seeprules_accepted_at is not None
                and owner.kyc_status == KYCStatus.APPROVED
            ),
        }

    def export_state(self) -> dict:
        owners: list[dict] = []
        for o in self._owners.values():
            owners.append({
                "owner_id": o.owner_id,
                "email": o.email,
                "password_hash": o.password_hash,
                "agreements_version": o.agreements_version,
                "agreements_accepted_at": o.agreements_accepted_at,
                "seeprules_version": o.seeprules_version,
                "seeprules_accepted_at": o.seeprules_accepted_at,
                "syntrendrules_version": o.syntrendrules_version,
                "syntrendrules_accepted_at": o.syntrendrules_accepted_at,
                "kyc_status": o.kyc_status.value,
                "kyc_full_name": o.kyc_full_name,
                "kyc_country": o.kyc_country,
                "kyc_submitted_at": o.kyc_submitted_at,
                "kyc_approved_at": o.kyc_approved_at,
                "kyc_inquiry_id": o.kyc_inquiry_id,
                "kyc_provider": o.kyc_provider,
                "agent_ids": list(o.agent_ids),
                "created_at": o.created_at,
            })
        return {"owners": owners, "email_index": dict(self._owners_by_email)}

    def import_state(self, data: dict) -> None:
        with self._lock:
            self._owners.clear()
            self._owners_by_email.clear()
            self._sessions.clear()
            for raw in data.get("owners", []):
                owner = Owner(
                    owner_id=raw["owner_id"],
                    email=raw["email"],
                    password_hash=raw["password_hash"],
                    agreements_version=raw.get("agreements_version"),
                    agreements_accepted_at=raw.get("agreements_accepted_at"),
                    seeprules_version=raw.get("seeprules_version"),
                    seeprules_accepted_at=raw.get("seeprules_accepted_at"),
                    syntrendrules_version=raw.get("syntrendrules_version"),
                    syntrendrules_accepted_at=raw.get("syntrendrules_accepted_at"),
                    kyc_status=KYCStatus(raw.get("kyc_status", KYCStatus.PENDING.value)),
                    kyc_full_name=raw.get("kyc_full_name", ""),
                    kyc_country=raw.get("kyc_country", ""),
                    kyc_submitted_at=raw.get("kyc_submitted_at"),
                    kyc_approved_at=raw.get("kyc_approved_at"),
                    kyc_inquiry_id=raw.get("kyc_inquiry_id"),
                    kyc_provider=raw.get("kyc_provider"),
                    agent_ids=list(raw.get("agent_ids", [])),
                    created_at=raw.get("created_at", time.time()),
                )
                self._owners[owner.owner_id] = owner
                self._owners_by_email[owner.email] = owner.owner_id
            for email, oid in data.get("email_index", {}).items():
                self._owners_by_email[email] = oid

    def _require_owner(self, owner_id: str) -> Owner:
        owner = self._owners.get(owner_id)
        if owner is None:
            raise OwnerError(f"unknown owner: {owner_id}")
        return owner

    @staticmethod
    def extract_bearer(authorization: str | None) -> str | None:
        if not authorization:
            return None
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        return authorization.strip()
