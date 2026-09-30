"""SynTrendsDemo: top-level orchestrator wiring the chain, wallets, fees,
AICoins, trading engine, Post-Freeze Order book, and Seepnews together
behind a small API-shaped surface (mirrors the real "agents can only act
through the API" rule from the spec).
"""

from __future__ import annotations

import time
from typing import Callable

from .aicoin import AICoin, AICoinError, create_aicoin
from .block import SynTrendsChain
from .fees import FeeEngine
from .freeze import FreezeState
from .orders import Fill, OrderError, PostFreezeOrder, PostFreezeOrderBook, TradingEngine
from .seepnews import Seepnews
from .wallet import WalletRegistry


class SynTrendsDemo:
    def __init__(
        self,
        cooldown_seconds: float = 15.0,
        pfo_timeout_seconds: float = 20.0,
        seepnews_cooldown_seconds: float = 5.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.clock = clock
        self.chain = SynTrendsChain()
        self.wallets = WalletRegistry()
        self.fees = FeeEngine(clock=clock)
        self.seepnews = Seepnews(cooldown_seconds=seepnews_cooldown_seconds, clock=clock)
        self.trading = TradingEngine(self.wallets, self.fees, self.chain, clock=clock)
        self.pfo_book = PostFreezeOrderBook(timeout_seconds=pfo_timeout_seconds, clock=clock)
        self.coins: dict[str, AICoin] = {}
        self.agents: set[str] = set()
        self._default_cooldown = cooldown_seconds

    # -- identity ------------------------------------------------------

    def register_agent(self, agent_id: str) -> None:
        self.agents.add(agent_id)
        self.chain.add_transaction("agent_register", {"agent_id": agent_id})

    def deposit_fiat(self, agent_id: str, amount: float) -> None:
        self.wallets.deposit_fiat(agent_id, amount)
        self.chain.add_transaction("fiat_deposit", {"agent_id": agent_id, "amount": amount})

    # -- AICoins ---------------------------------------------------------

    def launch_aicoin(
        self,
        ticker: str,
        name: str,
        creator_agent_id: str,
        total_supply: float,
        invest_fiat: float,
        pre_own_pct: float,
        mint_enabled: bool = False,
    ) -> AICoin:
        if self.wallets.fiat_balance(creator_agent_id) < invest_fiat - 1e-9:
            raise OrderError(f"agent {creator_agent_id} has insufficient fiat to launch this AICoin")

        coin = create_aicoin(
            ticker, name, creator_agent_id, total_supply, invest_fiat, pre_own_pct,
            mint_enabled=mint_enabled, cooldown_seconds=self._default_cooldown, clock=self.clock,
        )
        self.wallets.debit_fiat(creator_agent_id, invest_fiat)
        self.wallets.credit(creator_agent_id, coin.coin_id, coin.creator_coins)
        self.coins[coin.coin_id] = coin

        self.chain.add_transaction("aicoin_launch", {
            "coin_id": coin.coin_id, "ticker": coin.ticker, "creator": creator_agent_id,
            "total_supply": total_supply, "invest_fiat": invest_fiat,
            "pre_own_pct": pre_own_pct, "launch_price": coin.launch_price,
        })
        self.seepnews.system_post(
            "N-AICoin",
            f"New AICoin launched: ${coin.ticker} ({coin.name}) by {creator_agent_id} - "
            f"supply {total_supply:,.0f}, launch price ${coin.launch_price:.6f}, "
            f"pool ${coin.pool_fiat_reserve:,.2f}",
            mentions=[coin.ticker],
        )
        return coin

    # -- trading -----------------------------------------------------------

    def buy(self, agent_id: str, coin_id: str, fiat_amount: float) -> Fill:
        coin = self._get_coin(coin_id)
        was_frozen = coin.freeze.state == FreezeState.FROZEN
        fill = self.trading.buy(agent_id, coin, fiat_amount)
        self._post_freeze_transition_check(coin, was_frozen)
        return fill

    def sell(self, agent_id: str, coin_id: str, coin_amount: float) -> Fill:
        coin = self._get_coin(coin_id)
        was_frozen = coin.freeze.state == FreezeState.FROZEN
        fill = self.trading.sell(agent_id, coin, coin_amount)
        self._post_freeze_transition_check(coin, was_frozen)
        return fill

    def place_post_freeze_order(self, agent_id: str, coin_id: str, side: str, target_price: float, amount: float) -> PostFreezeOrder:
        coin = self._get_coin(coin_id)
        order = self.pfo_book.place(agent_id, coin, side, target_price, amount)
        self.chain.add_transaction("post_freeze_order", {
            "order_id": order.order_id, "agent_id": agent_id, "coin_id": coin_id,
            "side": side, "target_price": target_price, "amount": amount,
        })
        self.seepnews.system_post(
            "PostFreeze",
            f"Post-freeze order by {agent_id}: {side} {amount:,.2f} of ${coin.ticker} "
            f"at ${target_price:.6f}",
            mentions=[coin.ticker],
        )
        return order

    def tick(self, coin_id: str | None = None) -> list[PostFreezeOrder]:
        """Advance freeze state and resolve Post-Freeze Orders for one or
        all AICoins. Call periodically (or after time is advanced) even if
        no trade just happened, so cooldowns expire and PFOs can resolve.

        Returns orders that were just resolved (filled/refunded) this tick —
        `PostFreezeOrderBook.resolve()` pops them from its internal queue as
        soon as they resolve, so callers that want to report the outcome
        (e.g. the STP emitter) must capture this return value rather than
        re-querying the queue afterwards.
        """
        coins = [self._get_coin(coin_id)] if coin_id else list(self.coins.values())
        resolved: list[PostFreezeOrder] = []
        for coin in coins:
            was_frozen = coin.freeze.state == FreezeState.FROZEN
            coin.freeze.tick(coin.price)
            self._post_freeze_transition_check(coin, was_frozen)
            resolved.extend(self.pfo_book.resolve(coin, self.trading))
        return resolved

    def mine_block(self):
        return self.chain.mine_block()

    def leaderboard(self, by: str = "market_cap", limit: int = 10) -> list[AICoin]:
        coins = sorted(self.coins.values(), key=lambda c: getattr(c, by), reverse=True)
        return coins[:limit]

    # -- internals -----------------------------------------------------------

    def _get_coin(self, coin_id: str) -> AICoin:
        coin = self.coins.get(coin_id)
        if coin is None:
            raise AICoinError(f"unknown coin_id: {coin_id}")
        return coin

    def _post_freeze_transition_check(self, coin: AICoin, was_frozen: bool) -> None:
        if coin.freeze.state == FreezeState.FROZEN and not was_frozen:
            self.seepnews.system_post(
                "Freezes",
                f"${coin.ticker} hit a freeze ceiling at ${coin.freeze.ceiling:.6f}. "
                f"Upward orders locked for {coin.freeze.cooldown_seconds:.0f}s.",
                mentions=[coin.ticker],
            )
