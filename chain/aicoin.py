"""AICoin creation and launch pricing.

Reproduces the worked example in `syntrends.txt`:

    499k coins total, $50k starting fund/pool, 15% pre-own
    -> $0.1002 per coin at launch, holder owns 74,850 coins (15%)
       valued at $7,500, remaining free-coin pool value $42,500.

Derivation used here (see README/MINI_CHAIN.md for the algebra):

    launch_price       = invest_fiat / total_supply
    creator_coins      = total_supply * pre_own_pct
    pool_coin_reserve  = total_supply - creator_coins
    pool_fiat_reserve  = pool_coin_reserve * launch_price

This keeps `pool_fiat_reserve / pool_coin_reserve == launch_price` (so the
AMM in `orders.py` starts exactly at the advertised launch price) while
also making `creator_coins * launch_price == invest_fiat * pre_own_pct`,
matching the spec's numbers exactly regardless of `pre_own_pct`.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

from .freeze import FreezeEngine

MIN_SUPPLY = 1_000
MIN_INVEST_FIAT = 100.0
MAX_INVEST_FIAT = 500_000_000.0
MAX_PRE_OWN_PCT = 0.21


class AICoinError(Exception):
    pass


@dataclass
class AICoin:
    coin_id: str
    ticker: str
    name: str
    creator_agent_id: str
    total_supply: float
    pre_own_pct: float
    mint_enabled: bool
    is_corporate: bool
    launch_price: float
    pool_coin_reserve: float
    pool_fiat_reserve: float
    creator_coins: float
    freeze: FreezeEngine
    created_at: float = field(default_factory=time.time)

    @property
    def price(self) -> float:
        if self.pool_coin_reserve <= 0:
            return 0.0
        return self.pool_fiat_reserve / self.pool_coin_reserve

    @property
    def market_cap(self) -> float:
        return self.price * self.total_supply

    @property
    def k(self) -> float:
        """Constant-product invariant for the AMM in `orders.py`."""
        return self.pool_coin_reserve * self.pool_fiat_reserve


def create_aicoin(
    ticker: str,
    name: str,
    creator_agent_id: str,
    total_supply: float,
    invest_fiat: float,
    pre_own_pct: float,
    mint_enabled: bool = False,
    is_corporate: bool = False,
    cooldown_seconds: float = 15.0,
    clock: Callable[[], float] = time.time,
) -> AICoin:
    if total_supply < MIN_SUPPLY:
        raise AICoinError(f"total_supply must be >= {MIN_SUPPLY:,}")
    if not (MIN_INVEST_FIAT <= invest_fiat <= MAX_INVEST_FIAT):
        raise AICoinError(
            f"invest_fiat must be between ${MIN_INVEST_FIAT:,.0f} and ${MAX_INVEST_FIAT:,.0f}"
        )
    if not (0.0 <= pre_own_pct <= MAX_PRE_OWN_PCT):
        raise AICoinError(f"pre_own_pct must be between 0 and {MAX_PRE_OWN_PCT:.0%}")

    launch_price = invest_fiat / total_supply
    creator_coins = total_supply * pre_own_pct
    pool_coin_reserve = total_supply - creator_coins
    pool_fiat_reserve = pool_coin_reserve * launch_price

    return AICoin(
        coin_id=str(uuid.uuid4()),
        ticker=ticker.upper(),
        name=name,
        creator_agent_id=creator_agent_id,
        total_supply=total_supply,
        pre_own_pct=pre_own_pct,
        mint_enabled=mint_enabled,
        is_corporate=is_corporate,
        launch_price=launch_price,
        pool_coin_reserve=pool_coin_reserve,
        pool_fiat_reserve=pool_fiat_reserve,
        creator_coins=creator_coins,
        freeze=FreezeEngine(start_price=launch_price, cooldown_seconds=cooldown_seconds, clock=clock),
    )
