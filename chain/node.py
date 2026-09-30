"""ChainNode — standalone facade over SynTrendsDemo (Phase G).

Extracts the chain engine from the HTTP monolith so a testnet/mainnet node
can be reasoned about, seeded, and (eventually) run as its own process.
The API service still embeds a node in-process for now; this module is the
boundary other tooling (seed scripts, future RPC daemon) should import.
"""

from __future__ import annotations

from typing import Callable

from .clock import ManualClock
from .engine import SynTrendsDemo
from .state_io import dump_demo, load_demo


class ChainNode:
    """Public testnet / mainnet chain engine."""

    NETWORK_TESTNET = "syntrends-testnet-1"
    NETWORK_MAINNET = "syntrends-mainnet-1"

    def __init__(
        self,
        demo: SynTrendsDemo | None = None,
        clock: ManualClock | None = None,
        *,
        network: str = NETWORK_TESTNET,
    ) -> None:
        self.clock = clock or ManualClock(start=1_700_000_000.0)
        self.demo = demo or SynTrendsDemo(
            cooldown_seconds=10.0,
            pfo_timeout_seconds=15.0,
            seepnews_cooldown_seconds=0.0,
            clock=self.clock,
        )
        self.network = network

    @property
    def block_height(self) -> int:
        return len(self.demo.chain.chain)

    @property
    def agent_count(self) -> int:
        return len(self.demo.agents)

    @property
    def coin_count(self) -> int:
        return len(self.demo.coins)

    @property
    def latest_block_hash(self) -> str:
        if not self.demo.chain.chain:
            return ""
        return self.demo.chain.chain[-1].hash

    def export_state(self) -> dict:
        return dump_demo(self.demo, self.clock)

    def import_state(self, data: dict) -> None:
        self.demo = load_demo(data, self.clock)

    def status_dict(self) -> dict:
        return {
            "network": self.network,
            "block_height": self.block_height,
            "latest_block_hash": self.latest_block_hash,
            "agents": self.agent_count,
            "coins": self.coin_count,
            "protocol": "STP/1.0",
        }
