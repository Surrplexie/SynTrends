"""Owner $syntrends cash ledger — chip pool, then allocate to agents.

Owner balance is NOT an agent wallet. Allocate credits agent FIAT (the same
chip). Recall pulls unused agent chip back. Simulated owner credit is
testnet/demo only; live money will replace credit with a partner webhook.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass


class OwnerCashError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class CashEntry:
    entry_id: str
    ts: float
    owner_id: str
    kind: str  # credit | allocate | recall
    amount: float
    agent_id: str | None = None
    note: str = ""

    def public(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "ts": self.ts,
            "kind": self.kind,
            "amount": self.amount,
            "agent_id": self.agent_id,
            "note": self.note,
        }


class OwnerCashLedger:
    def __init__(self) -> None:
        self._balances: dict[str, float] = {}
        self._entries: list[CashEntry] = []
        self._credit_last: dict[str, float] = {}
        self._partner_ids: dict[str, str] = {}
        self._lock = threading.RLock()

    def balance(self, owner_id: str) -> float:
        return self._balances.get(owner_id, 0.0)

    def credit_last(self, owner_id: str) -> float:
        return self._credit_last.get(owner_id, 0.0)

    def entries_for(self, owner_id: str, *, limit: int = 50) -> list[CashEntry]:
        rows = [e for e in self._entries if e.owner_id == owner_id]
        return rows[-limit:]

    def credit(self, owner_id: str, amount: float, *, note: str = "simulated") -> CashEntry:
        if amount <= 0:
            raise OwnerCashError("credit amount must be positive")
        with self._lock:
            self._balances[owner_id] = self._balances.get(owner_id, 0.0) + amount
            entry = self._append(owner_id, "credit", amount, note=note)
            self._credit_last[owner_id] = entry.ts
            return entry

    def debit_owner(self, owner_id: str, amount: float) -> None:
        if amount <= 0:
            raise OwnerCashError("amount must be positive")
        with self._lock:
            bal = self._balances.get(owner_id, 0.0)
            if bal < amount - 1e-9:
                raise OwnerCashError(
                    f"owner chip balance {bal:.2f} is less than {amount:.2f}"
                )
            self._balances[owner_id] = bal - amount

    def credit_owner_only(self, owner_id: str, amount: float) -> None:
        if amount <= 0:
            raise OwnerCashError("amount must be positive")
        with self._lock:
            self._balances[owner_id] = self._balances.get(owner_id, 0.0) + amount

    def apply_partner_credit(
        self,
        owner_id: str,
        amount: float,
        *,
        external_id: str,
    ) -> tuple[CashEntry, bool]:
        """Credit owner chip from a partner event. Duplicate external_id is a no-op."""
        if amount <= 0:
            raise OwnerCashError("credit amount must be positive")
        with self._lock:
            prior = self._partner_ids.get(external_id)
            if prior:
                for e in reversed(self._entries):
                    if e.entry_id == prior:
                        return e, True
                return CashEntry(
                    entry_id=prior,
                    ts=0,
                    owner_id=owner_id,
                    kind="partner",
                    amount=amount,
                    note=external_id,
                ), True
            self._balances[owner_id] = self._balances.get(owner_id, 0.0) + amount
            entry = self._append(
                owner_id, "partner", amount, note=f"partner:{external_id}"
            )
            self._partner_ids[external_id] = entry.entry_id
            return entry, False

    def record_allocate(self, owner_id: str, agent_id: str, amount: float) -> CashEntry:
        with self._lock:
            return self._append(owner_id, "allocate", amount, agent_id=agent_id)

    def record_recall(self, owner_id: str, agent_id: str, amount: float) -> CashEntry:
        with self._lock:
            return self._append(owner_id, "recall", amount, agent_id=agent_id)

    def _append(
        self,
        owner_id: str,
        kind: str,
        amount: float,
        *,
        agent_id: str | None = None,
        note: str = "",
    ) -> CashEntry:
        entry = CashEntry(
            entry_id=secrets.token_hex(8),
            ts=time.time(),
            owner_id=owner_id,
            kind=kind,
            amount=amount,
            agent_id=agent_id,
            note=note,
        )
        self._entries.append(entry)
        if len(self._entries) > 10_000:
            self._entries = self._entries[-8_000:]
        return entry

    def export_state(self) -> dict:
        return {
            "balances": dict(self._balances),
            "credit_last": dict(self._credit_last),
            "partner_ids": dict(self._partner_ids),
            "entries": [
                {
                    "entry_id": e.entry_id,
                    "ts": e.ts,
                    "owner_id": e.owner_id,
                    "kind": e.kind,
                    "amount": e.amount,
                    "agent_id": e.agent_id,
                    "note": e.note,
                }
                for e in self._entries
            ],
        }

    def import_state(self, data: dict) -> None:
        with self._lock:
            self._balances = {
                str(k): float(v) for k, v in (data.get("balances") or {}).items()
            }
            self._credit_last = {
                str(k): float(v) for k, v in (data.get("credit_last") or {}).items()
            }
            self._partner_ids = {
                str(k): str(v) for k, v in (data.get("partner_ids") or {}).items()
            }
            self._entries = []
            for raw in data.get("entries") or []:
                self._entries.append(
                    CashEntry(
                        entry_id=raw.get("entry_id") or secrets.token_hex(8),
                        ts=float(raw.get("ts") or 0),
                        owner_id=raw["owner_id"],
                        kind=raw.get("kind", "credit"),
                        amount=float(raw.get("amount") or 0),
                        agent_id=raw.get("agent_id"),
                        note=raw.get("note") or "",
                    )
                )
