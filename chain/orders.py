"""Trading engine: constant-product AMM pool per AICoin, freeze-ceiling
enforcement on buys, dynamic fees, and Post-Freeze Order queues.

Simplification: the single trade that first crosses a freeze threshold is
allowed to complete in full (using whatever amount the agent requested);
only the *next* buy attempt is rejected once the coin is actually frozen.
A production system would clip the fill exactly at the ceiling and refund
the remainder. This keeps the demo's trade math simple and easy to test
while still faithfully demonstrating "no buys above the ceiling while
frozen."
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

from .aicoin import AICoin
from .fees import FeeEngine
from .freeze import FreezeState
from .wallet import WalletRegistry


class OrderError(Exception):
    pass


@dataclass
class Fill:
    order_id: str
    agent_id: str
    coin_id: str
    side: str  # "buy" | "sell"
    fiat_amount: float
    coin_amount: float
    fee_paid: float
    price_after: float
    timestamp: float = field(default_factory=time.time)


class TradingEngine:
    def __init__(
        self,
        wallets: WalletRegistry,
        fees: FeeEngine,
        chain,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.wallets = wallets
        self.fees = fees
        self.chain = chain
        self.clock = clock

    def buy(self, agent_id: str, coin: AICoin, fiat_amount: float) -> Fill:
        if fiat_amount <= 0:
            raise OrderError("fiat_amount must be positive")
        coin.freeze.tick(coin.price)

        if self.wallets.fiat_balance(agent_id) < fiat_amount - 1e-9:
            raise OrderError(
                f"agent {agent_id} has insufficient fiat balance for a ${fiat_amount:,.2f} buy"
            )

        fee_pct = self.fees.current_fee(agent_id, coin.coin_id)
        fee_amount = fiat_amount * (fee_pct / 100.0)
        net_fiat_in = fiat_amount - fee_amount

        k = coin.k
        new_fiat_reserve = coin.pool_fiat_reserve + net_fiat_in
        new_coin_reserve = k / new_fiat_reserve
        coin_out = coin.pool_coin_reserve - new_coin_reserve
        if coin_out <= 0:
            raise OrderError("trade too small to fill")

        projected_price = new_fiat_reserve / new_coin_reserve
        if not coin.freeze.is_buy_allowed(projected_price):
            raise OrderError(
                f"buy rejected: ${coin.ticker} is frozen at ${coin.freeze.ceiling:.8f}; "
                f"this order would push price to ${projected_price:.8f}"
            )

        self.wallets.debit_fiat(agent_id, fiat_amount)
        self.fees.record_transaction(agent_id, coin.coin_id)
        coin.pool_fiat_reserve = new_fiat_reserve
        coin.pool_coin_reserve = new_coin_reserve
        self.wallets.credit(agent_id, coin.coin_id, coin_out)
        coin.freeze.tick(coin.price)

        fill = Fill(
            order_id=str(uuid.uuid4()),
            agent_id=agent_id,
            coin_id=coin.coin_id,
            side="buy",
            fiat_amount=fiat_amount,
            coin_amount=coin_out,
            fee_paid=fee_amount,
            price_after=coin.price,
        )
        self.chain.add_transaction("trade", {
            "order_id": fill.order_id, "agent_id": agent_id, "coin_id": coin.coin_id,
            "side": "buy", "fiat_amount": fiat_amount, "coin_amount": coin_out,
            "fee": fee_amount, "price_after": coin.price,
        })
        return fill

    def sell(self, agent_id: str, coin: AICoin, coin_amount: float) -> Fill:
        if coin_amount <= 0:
            raise OrderError("coin_amount must be positive")
        coin.freeze.tick(coin.price)  # selling never blocked, but keep state fresh

        if self.wallets.balance(agent_id, coin.coin_id) < coin_amount - 1e-9:
            raise OrderError(f"agent {agent_id} has insufficient {coin.ticker} balance to sell")

        k = coin.k
        new_coin_reserve = coin.pool_coin_reserve + coin_amount
        new_fiat_reserve = k / new_coin_reserve
        gross_fiat_out = coin.pool_fiat_reserve - new_fiat_reserve
        if gross_fiat_out <= 0:
            raise OrderError("trade too small to fill")

        fee_pct = self.fees.current_fee(agent_id, coin.coin_id)
        fee_amount = gross_fiat_out * (fee_pct / 100.0)
        net_fiat_out = gross_fiat_out - fee_amount

        self.wallets.debit(agent_id, coin.coin_id, coin_amount)
        self.fees.record_transaction(agent_id, coin.coin_id)
        coin.pool_coin_reserve = new_coin_reserve
        coin.pool_fiat_reserve = new_fiat_reserve
        self.wallets.deposit_fiat(agent_id, net_fiat_out)
        coin.freeze.tick(coin.price)

        fill = Fill(
            order_id=str(uuid.uuid4()),
            agent_id=agent_id,
            coin_id=coin.coin_id,
            side="sell",
            fiat_amount=net_fiat_out,
            coin_amount=coin_amount,
            fee_paid=fee_amount,
            price_after=coin.price,
        )
        self.chain.add_transaction("trade", {
            "order_id": fill.order_id, "agent_id": agent_id, "coin_id": coin.coin_id,
            "side": "sell", "fiat_amount": net_fiat_out, "coin_amount": coin_amount,
            "fee": fee_amount, "price_after": coin.price,
        })
        return fill


@dataclass
class PostFreezeOrder:
    order_id: str
    agent_id: str
    coin_id: str
    side: str  # "buy" | "sell"
    target_price: float
    amount: float  # fiat amount for a buy, coin amount for a sell
    placed_at: float
    filled_amount: float = 0.0
    status: str = "pending"  # pending | filled | refunded | cancelled


class PostFreezeOrderBook:
    """First-come-first-served conditional orders placed only during an
    active freeze. One order per agent per AICoin; editing an order resets
    its place in the FCFS queue (implemented as overwriting `placed_at`).
    Orders that never reach their target price within `timeout_seconds`
    (a compressed stand-in for the spec's 4 days) are refunded.
    """

    def __init__(self, timeout_seconds: float = 4 * 24 * 3600, clock: Callable[[], float] = time.time):
        self.timeout_seconds = timeout_seconds
        self.clock = clock
        self.orders: dict[str, dict[str, PostFreezeOrder]] = {}  # coin_id -> agent_id -> order

    def place(self, agent_id: str, coin: AICoin, side: str, target_price: float, amount: float) -> PostFreezeOrder:
        if coin.freeze.state != FreezeState.FROZEN:
            raise OrderError("post-freeze orders may only be placed while a freeze is active")
        if side not in ("buy", "sell"):
            raise OrderError("side must be 'buy' or 'sell'")
        if amount <= 0 or target_price <= 0:
            raise OrderError("amount and target_price must be positive")

        book = self.orders.setdefault(coin.coin_id, {})
        order = PostFreezeOrder(
            order_id=str(uuid.uuid4()),
            agent_id=agent_id,
            coin_id=coin.coin_id,
            side=side,
            target_price=target_price,
            amount=amount,
            placed_at=self.clock(),
        )
        book[agent_id] = order  # replaces any prior order, sending it to the back of the queue
        return order

    def cancel(self, agent_id: str, coin_id: str) -> PostFreezeOrder | None:
        book = self.orders.get(coin_id, {})
        order = book.pop(agent_id, None)
        if order:
            order.status = "cancelled"
        return order

    def queue(self, coin_id: str) -> list[PostFreezeOrder]:
        book = self.orders.get(coin_id, {})
        return sorted(book.values(), key=lambda o: o.placed_at)

    def resolve(self, coin: AICoin, trading_engine: TradingEngine) -> list[PostFreezeOrder]:
        """Attempt to fill queued orders in FCFS order once conditions allow."""
        book = self.orders.get(coin.coin_id, {})
        now = self.clock()
        resolved: list[PostFreezeOrder] = []

        for order in self.queue(coin.coin_id):
            if order.status != "pending":
                continue

            reached = (
                (order.side == "buy" and coin.price >= order.target_price)
                or (order.side == "sell" and coin.price <= order.target_price)
            )
            expired = (now - order.placed_at) >= self.timeout_seconds

            if reached:
                try:
                    if order.side == "buy":
                        trading_engine.buy(order.agent_id, coin, order.amount)
                    else:
                        trading_engine.sell(order.agent_id, coin, order.amount)
                    order.filled_amount = order.amount
                    order.status = "filled"
                    trading_engine.fees.reset_after_post_freeze_order(order.agent_id, coin.coin_id)
                except OrderError:
                    order.status = "refunded"
            elif expired:
                order.status = "refunded"

            if order.status != "pending":
                resolved.append(order)
                book.pop(order.agent_id, None)

        return resolved
