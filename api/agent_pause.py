"""Owner-controlled agent pause / resume (Phase J).

Pausing halts agent **writes** (trades, posts, faucet, deposits) while preserving
chain state. Reads (snapshot, streams) continue. Resume may optionally enforce a
short gradual window before writes are allowed again.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


class AgentPauseError(Exception):
    pass


@dataclass
class AgentPauseRecord:
    paused: bool = False
    paused_at: float | None = None
    paused_by_owner_id: str | None = None
    gradual_resume_until: float | None = None
    resumed_at: float | None = None


class AgentPauseRegistry:
    """Per-agent pause state keyed by ``agent_id``."""

    def __init__(self) -> None:
        self._records: dict[str, AgentPauseRecord] = {}
        self._lock = threading.RLock()

    def pause(self, owner_id: str, agent_id: str) -> AgentPauseRecord:
        agent_id = agent_id.strip()
        with self._lock:
            rec = self._records.setdefault(agent_id, AgentPauseRecord())
            rec.paused = True
            rec.paused_at = time.time()
            rec.paused_by_owner_id = owner_id
            rec.gradual_resume_until = None
            rec.resumed_at = None
            return rec

    def resume(self, owner_id: str, agent_id: str, *, gradual_seconds: float = 0) -> AgentPauseRecord:
        agent_id = agent_id.strip()
        gradual_seconds = max(0.0, float(gradual_seconds))
        with self._lock:
            rec = self._records.setdefault(agent_id, AgentPauseRecord())
            now = time.time()
            rec.paused = False
            rec.paused_by_owner_id = owner_id
            rec.resumed_at = now
            rec.gradual_resume_until = now + gradual_seconds if gradual_seconds > 0 else None
            return rec

    def write_block_reason(self, agent_id: str) -> tuple[bool, str]:
        """Return ``(blocked, message)`` when agent writes must be rejected."""
        if not agent_id:
            return False, ""
        with self._lock:
            rec = self._records.get(agent_id)
            if rec is None:
                return False, ""
            if rec.paused:
                return True, "agent paused by owner — resume via owner portal"
            if rec.gradual_resume_until is not None:
                now = time.time()
                if now < rec.gradual_resume_until:
                    remaining = max(1, int(rec.gradual_resume_until - now))
                    return True, f"gradual resume active — try again in {remaining}s"
                rec.gradual_resume_until = None
            return False, ""

    def public_status(self, agent_id: str) -> dict:
        with self._lock:
            rec = self._records.get(agent_id)
            if rec is None:
                return {
                    "agent_id": agent_id,
                    "paused": False,
                    "paused_at": None,
                    "gradual_resume_until": None,
                    "writes_blocked": False,
                }
            blocked, _ = self.write_block_reason(agent_id)
            return {
                "agent_id": agent_id,
                "paused": rec.paused,
                "paused_at": rec.paused_at,
                "gradual_resume_until": rec.gradual_resume_until,
                "writes_blocked": blocked,
            }

    def paused_count(self) -> int:
        with self._lock:
            return sum(1 for rec in self._records.values() if rec.paused)

    def export_state(self) -> dict[str, dict]:
        with self._lock:
            out: dict[str, dict] = {}
            for agent_id, rec in self._records.items():
                if not rec.paused and rec.gradual_resume_until is None and rec.paused_at is None:
                    continue
                out[agent_id] = {
                    "paused": rec.paused,
                    "paused_at": rec.paused_at,
                    "paused_by_owner_id": rec.paused_by_owner_id,
                    "gradual_resume_until": rec.gradual_resume_until,
                    "resumed_at": rec.resumed_at,
                }
            return out

    def import_state(self, data: dict[str, dict]) -> None:
        with self._lock:
            self._records.clear()
            for agent_id, raw in data.items():
                self._records[agent_id] = AgentPauseRecord(
                    paused=bool(raw.get("paused", False)),
                    paused_at=raw.get("paused_at"),
                    paused_by_owner_id=raw.get("paused_by_owner_id"),
                    gradual_resume_until=raw.get("gradual_resume_until"),
                    resumed_at=raw.get("resumed_at"),
                )
