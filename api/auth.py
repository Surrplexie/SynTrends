"""API key authentication: Agent API keys vs 3rdPS API keys.

These are **different credential classes** for **different products**:

- **Agent API** (`st_agent_*`, ``KeyKind.AGENT``) — one bound ``agent_id``; read + write; wallet.
- **3rdPS API** (`st_thirdps_*`, ``KeyKind.THIRDPSS``) — vendor read-only intake; **no** wallet, **no** writes.

Legacy demo keys may still use ``st_license_*`` / stored kind ``license``; they are treated as 3rdPS, not Agent API.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from enum import Enum

from .curation import invoice_usd


class KeyKind(str, Enum):
    AGENT = "agent"
    THIRDPSS = "thirdps"


def normalize_key_kind(value: str) -> KeyKind:
    """Map persisted ``license`` rows to ``thirdps``."""
    if value == "license":
        return KeyKind.THIRDPSS
    return KeyKind(value)


def is_thirdps_key(key: "APIKey") -> bool:
    return key.kind == KeyKind.THIRDPSS


def is_agent_key(key: "APIKey") -> bool:
    return key.kind == KeyKind.AGENT


# Production intent: calendar expiry still happens; issuance is free.
THIRDPS_DEFAULT_TTL_SECONDS = 365 * 24 * 3600.0
# Demo invoice: amount_due = invoice_CT × usd_per_CT. Unused raw CT → $0.
THIRDPS_DEFAULT_USD_PER_CT = 0.001
THIRDPS_DEFAULT_USD_PER_WEIGHT = THIRDPS_DEFAULT_USD_PER_CT  # alias


@dataclass
class APIKey:
    token: str
    kind: KeyKind
    agent_id: str | None = None
    label: str = ""
    owner_id: str | None = None
    created_at: float = field(default_factory=time.time)
    revoked_at: float | None = None
    expires_at: float | None = None
    usage_weight: float = 0.0  # raw Curation Tokens (CT) before bundle × network load
    product_classes: set[str] = field(default_factory=set)

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and time.time() >= self.expires_at

    def invoice_amount(self, usd_per_ct: float, *, global_agents: int | float = 0) -> float:
        """Issuance is $0. Owed = invoice CT × USD/CT. Never-used → 0."""
        if self.kind != KeyKind.THIRDPSS:
            return 0.0
        return invoice_usd(self.usage_weight, self.product_classes, global_agents, usd_per_ct)


class AuthError(Exception):
    pass


class KeyStore:
    """In-memory key registry."""

    def __init__(self) -> None:
        self._keys: dict[str, APIKey] = {}

    def issue_agent_key(
        self,
        agent_id: str,
        label: str = "",
        *,
        owner_id: str | None = None,
    ) -> APIKey:
        token = f"st_agent_{secrets.token_hex(16)}"
        key = APIKey(
            token=token,
            kind=KeyKind.AGENT,
            agent_id=agent_id,
            label=label or agent_id,
            owner_id=owner_id,
        )
        self._keys[token] = key
        return key

    def issue_thirdps_key(
        self,
        label: str = "thirdps-vendor",
        *,
        owner_id: str | None = None,
        ttl_seconds: float = THIRDPS_DEFAULT_TTL_SECONDS,
    ) -> APIKey:
        """Issue a **3rdPS API** read-only key — free to mint; still expires; bill in CT."""
        token = f"st_thirdps_{secrets.token_hex(16)}"
        now = time.time()
        key = APIKey(
            token=token,
            kind=KeyKind.THIRDPSS,
            label=label,
            owner_id=owner_id,
            created_at=now,
            expires_at=now + max(1.0, float(ttl_seconds)),
            usage_weight=0.0,
        )
        self._keys[token] = key
        return key

    def issue_license_key(self, label: str = "chart-vendor", *, owner_id: str | None = None) -> APIKey:
        """Deprecated alias — issues ``st_thirdps_*`` (3rdPS API), not Agent API."""
        return self.issue_thirdps_key(label or "chart-vendor", owner_id=owner_id)

    def register(self, key: APIKey) -> None:
        self._keys[key.token] = key

    def lookup(self, token: str | None) -> APIKey:
        if not token:
            raise AuthError("missing API key")
        key = self._keys.get(token)
        if key is None:
            raise AuthError("invalid API key")
        if key.is_revoked:
            raise AuthError("API key has been revoked")
        if key.is_expired:
            raise AuthError("API key has expired")
        return key

    def revoke(self, token: str) -> APIKey:
        key = self.lookup(token)
        key.revoked_at = time.time()
        return key

    def list_for_owner(self, owner_id: str) -> list[APIKey]:
        return [k for k in self._keys.values() if k.owner_id == owner_id and not k.is_revoked]

    def list_for_agent(self, agent_id: str) -> list[APIKey]:
        return [
            k
            for k in self._keys.values()
            if k.agent_id == agent_id and k.kind == KeyKind.AGENT and not k.is_revoked
        ]

    def allows_write(self, key: APIKey) -> bool:
        return key.kind == KeyKind.AGENT

    def export_state(self) -> list[dict]:
        return [
            {
                "token": k.token,
                "kind": k.kind.value,
                "agent_id": k.agent_id,
                "label": k.label,
                "owner_id": k.owner_id,
                "created_at": k.created_at,
                "revoked_at": k.revoked_at,
                "expires_at": k.expires_at,
                "usage_weight": k.usage_weight,
                "product_classes": sorted(k.product_classes),
            }
            for k in self._keys.values()
        ]

    def import_state(self, items: list[dict]) -> None:
        self._keys.clear()
        for item in items:
            key = APIKey(
                token=item["token"],
                kind=normalize_key_kind(item["kind"]),
                agent_id=item.get("agent_id"),
                label=item.get("label", ""),
                owner_id=item.get("owner_id"),
                created_at=item.get("created_at", time.time()),
                revoked_at=item.get("revoked_at"),
                expires_at=item.get("expires_at"),
                usage_weight=float(item.get("usage_weight") or 0.0),
                product_classes=set(item.get("product_classes") or []),
            )
            self._keys[key.token] = key

    def first_agent_key(self) -> APIKey | None:
        for key in self._keys.values():
            if key.kind == KeyKind.AGENT and not key.is_revoked:
                return key
        return None

    def first_thirdps_key(self) -> APIKey | None:
        for key in self._keys.values():
            if is_thirdps_key(key) and not key.is_revoked:
                return key
        return None

    def first_license_key(self) -> APIKey | None:
        """Deprecated alias for :meth:`first_thirdps_key`."""
        return self.first_thirdps_key()

    @staticmethod
    def extract_bearer(authorization: str | None) -> str | None:
        if not authorization:
            return None
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        return authorization.strip()
