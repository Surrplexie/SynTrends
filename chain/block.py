"""Minimal SynTrends chain: SHA-3 hashed blocks holding transaction logs.

Per the spec, agents can *read* the chain but never post to it directly —
only the trading engine / AICoin issuance / Seepnews layers append
transactions on an agent's behalf via `add_transaction`. This is a demo
proof-of-work chain (single low difficulty target) purely to demonstrate
hash-chaining and tamper detection; it is not a real distributed network.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Transaction:
    tx_type: str
    payload: dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"tx_type": self.tx_type, "payload": self.payload, "timestamp": self.timestamp}


@dataclass
class Block:
    index: int
    timestamp: float
    transactions: list[Transaction]
    previous_hash: str
    nonce: int = 0
    hash: str = ""

    def compute_hash(self) -> str:
        block_data = {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": [t.to_dict() for t in self.transactions],
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
        }
        encoded = json.dumps(block_data, sort_keys=True, default=str).encode()
        return hashlib.sha3_256(encoded).hexdigest()


class SynTrendsChain:
    """Toy proof-of-work chain: hashes must start with `DIFFICULTY_PREFIX`."""

    DIFFICULTY_PREFIX = "0"

    def __init__(self) -> None:
        self.chain: list[Block] = []
        self.pending: list[Transaction] = []
        self._create_genesis_block()

    def _create_genesis_block(self) -> None:
        genesis = Block(index=0, timestamp=time.time(), transactions=[], previous_hash="0" * 64)
        genesis.hash = self._mine(genesis)
        self.chain.append(genesis)

    def _mine(self, block: Block) -> str:
        block.nonce = 0
        digest = block.compute_hash()
        while not digest.startswith(self.DIFFICULTY_PREFIX):
            block.nonce += 1
            digest = block.compute_hash()
        return digest

    @property
    def last_block(self) -> Block:
        return self.chain[-1]

    def add_transaction(self, tx_type: str, payload: dict[str, Any]) -> Transaction:
        tx = Transaction(tx_type=tx_type, payload=payload)
        self.pending.append(tx)
        return tx

    def mine_block(self) -> Block | None:
        if not self.pending:
            return None
        block = Block(
            index=len(self.chain),
            timestamp=time.time(),
            transactions=self.pending,
            previous_hash=self.last_block.hash,
        )
        block.hash = self._mine(block)
        self.chain.append(block)
        self.pending = []
        return block

    def is_valid(self) -> bool:
        for i in range(1, len(self.chain)):
            current, previous = self.chain[i], self.chain[i - 1]
            if current.previous_hash != previous.hash:
                return False
            if current.hash != current.compute_hash():
                return False
            if not current.hash.startswith(self.DIFFICULTY_PREFIX):
                return False
        return True

    def all_transactions(self):
        for block in self.chain:
            for tx in block.transactions:
                yield block.index, tx
