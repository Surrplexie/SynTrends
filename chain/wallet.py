"""Wallet registry enforcing the spec's immutable mapping:

    agent_id -> AICoin_id -> wallet_address

Once a wallet is created for an (agent, coin) pair it is never replaced.
Fiat is tracked separately per agent as a first-class balance, per the
spec's "fiat must be treated as a first-class asset" rule.
"""

from __future__ import annotations

import hashlib
import secrets


class InsufficientBalance(Exception):
    pass


class WalletRegistry:
    def __init__(self) -> None:
        self._wallets: dict[tuple[str, str], str] = {}
        self._coin_balances: dict[str, float] = {}  # wallet_address -> balance
        self._fiat_balances: dict[str, float] = {}  # agent_id -> fiat balance

    # -- wallet identity -------------------------------------------------

    def get_or_create_wallet(self, agent_id: str, coin_id: str) -> str:
        key = (agent_id, coin_id)
        existing = self._wallets.get(key)
        if existing is not None:
            return existing
        seed = f"{agent_id}:{coin_id}:{secrets.token_hex(8)}".encode()
        address = "0x" + hashlib.sha3_256(seed).hexdigest()[:40]
        self._wallets[key] = address
        self._coin_balances[address] = 0.0
        return address

    def wallet_for(self, agent_id: str, coin_id: str) -> str | None:
        return self._wallets.get((agent_id, coin_id))

    # -- AICoin balances ---------------------------------------------------

    def balance(self, agent_id: str, coin_id: str) -> float:
        address = self.wallet_for(agent_id, coin_id)
        return self._coin_balances.get(address, 0.0) if address else 0.0

    def credit(self, agent_id: str, coin_id: str, amount: float) -> None:
        if amount < 0:
            raise ValueError("credit amount must be non-negative")
        address = self.get_or_create_wallet(agent_id, coin_id)
        self._coin_balances[address] += amount

    def debit(self, agent_id: str, coin_id: str, amount: float) -> None:
        if amount < 0:
            raise ValueError("debit amount must be non-negative")
        address = self.wallet_for(agent_id, coin_id)
        balance = self._coin_balances.get(address, 0.0) if address else 0.0
        if address is None or balance < amount - 1e-9:
            raise InsufficientBalance(
                f"agent {agent_id} has {balance} of coin {coin_id}, cannot debit {amount}"
            )
        self._coin_balances[address] = balance - amount

    # -- fiat balances -----------------------------------------------------

    def fiat_balance(self, agent_id: str) -> float:
        return self._fiat_balances.get(agent_id, 0.0)

    def deposit_fiat(self, agent_id: str, amount: float) -> None:
        if amount < 0:
            raise ValueError("deposit amount must be non-negative")
        self._fiat_balances[agent_id] = self._fiat_balances.get(agent_id, 0.0) + amount

    def debit_fiat(self, agent_id: str, amount: float) -> None:
        if amount < 0:
            raise ValueError("debit amount must be non-negative")
        balance = self._fiat_balances.get(agent_id, 0.0)
        if balance < amount - 1e-9:
            raise InsufficientBalance(
                f"agent {agent_id} has ${balance:.2f} fiat, cannot debit ${amount:.2f}"
            )
        self._fiat_balances[agent_id] = balance - amount
