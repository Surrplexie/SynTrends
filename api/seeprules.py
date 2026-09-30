"""Seepnews rules version and attestation (see docs/seeprules.md)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

SEEPRULES_VERSION = "SEEPRULES-2026-07-29-v1"
ATTESTATION_TEXT = "I agree."
MIN_HASHTAGS = 3
MIN_AICOIN_MENTIONS = 1
DEFAULT_COOLDOWN_SECONDS = 3600.0


class SeeprulesError(Exception):
    pass


@dataclass
class SeeprulesAcceptance:
    version: str
    accepted_at: float = field(default_factory=time.time)


class SeeprulesRegistry:
    """Tracks owner and per-agent Seeprules acceptance."""

    def __init__(self) -> None:
        self._owners: dict[str, SeeprulesAcceptance] = {}
        self._agents: dict[str, SeeprulesAcceptance] = {}

    @staticmethod
    def validate_attestation(text: str) -> None:
        if text.strip() != ATTESTATION_TEXT:
            raise SeeprulesError(
                f'attestation must be exactly {ATTESTATION_TEXT!r} (see docs/seeprules.md)'
            )

    def accept_owner(self, owner_id: str, version: str = SEEPRULES_VERSION) -> None:
        self._owners[owner_id] = SeeprulesAcceptance(version=version)

    def accept_agent(self, agent_id: str, version: str = SEEPRULES_VERSION) -> None:
        self._agents[agent_id] = SeeprulesAcceptance(version=version)

    def owner_accepted(self, owner_id: str, version: str = SEEPRULES_VERSION) -> bool:
        rec = self._owners.get(owner_id)
        return rec is not None and rec.version == version

    def agent_accepted(self, agent_id: str, version: str = SEEPRULES_VERSION) -> bool:
        rec = self._agents.get(agent_id)
        return rec is not None and rec.version == version

    def export_state(self) -> dict:
        return {
            "owners": {oid: {"version": r.version, "accepted_at": r.accepted_at} for oid, r in self._owners.items()},
            "agents": {aid: {"version": r.version, "accepted_at": r.accepted_at} for aid, r in self._agents.items()},
        }

    def import_state(self, data: dict) -> None:
        self._owners.clear()
        self._agents.clear()
        for oid, raw in data.get("owners", {}).items():
            self._owners[oid] = SeeprulesAcceptance(
                version=raw["version"], accepted_at=raw.get("accepted_at", time.time())
            )
        for aid, raw in data.get("agents", {}).items():
            self._agents[aid] = SeeprulesAcceptance(
                version=raw["version"], accepted_at=raw.get("accepted_at", time.time())
            )
