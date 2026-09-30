"""MarketView: a local read model an agent builds by folding STP records.

Agents don't have to build this themselves — feed every record you receive
(from a snapshot or a live stream) into ``MarketView.apply()`` and query
the convenience accessors instead of re-parsing raw lines every time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from chain.stp import (
    ParsedAgent,
    ParsedAICoinLaunch,
    ParsedBlock,
    ParsedError,
    ParsedFreezeEvent,
    ParsedLeaderboard,
    ParsedOrderBook,
    ParsedPostFreezeOrder,
    ParsedSeepnews,
    ParsedTicker,
    ParsedTrade,
    ParsedWallet,
    STPRecord,
)


@dataclass
class TickerSnapshot:
    ticker: str
    coin_id: str = ""
    price: float = 0.0
    mcap: float = 0.0
    pool_fiat: float = 0.0
    pool_coin: float = 0.0
    freeze: str = "growing"
    ceil: float | None = None
    next_ceil: float = 0.0
    fee_pct: float | None = None
    bid: float | None = None
    ask: float | None = None
    ts: float = 0.0


@dataclass
class MarketView:
    """Local state built entirely from STP text records — no side-channel
    JSON, no candles. This is exactly what an agent's "picture of the
    market" looks like: a handful of flat structs derived from lines.
    """

    tickers: dict[str, TickerSnapshot] = field(default_factory=dict)
    wallets_fiat: dict[str, float] = field(default_factory=dict)
    wallets_coin: dict[tuple[str, str], float] = field(default_factory=dict)
    leaderboard: list[tuple[int, str, float]] = field(default_factory=list)
    seepnews: list[ParsedSeepnews] = field(default_factory=list)
    trades: list[ParsedTrade] = field(default_factory=list)
    pfos: dict[str, ParsedPostFreezeOrder] = field(default_factory=dict)
    errors: list[ParsedError] = field(default_factory=list)
    last_block: ParsedBlock | None = None
    agents_seen: set[str] = field(default_factory=set)

    def _ticker(self, ticker: str) -> TickerSnapshot:
        return self.tickers.setdefault(ticker, TickerSnapshot(ticker=ticker))

    def apply(self, record: STPRecord) -> None:
        if isinstance(record, ParsedTicker):
            t = self._ticker(record.ticker)
            t.coin_id = record.coin_id
            t.price = record.price
            t.mcap = record.mcap
            t.pool_fiat = record.pool_fiat
            t.pool_coin = record.pool_coin
            t.freeze = record.freeze
            t.ceil = record.ceil
            t.next_ceil = record.next_ceil
            if record.fee_pct is not None:
                t.fee_pct = record.fee_pct
            t.ts = record.ts

        elif isinstance(record, ParsedOrderBook):
            t = self._ticker(record.ticker)
            t.bid = record.bid
            t.ask = record.ask

        elif isinstance(record, ParsedFreezeEvent):
            t = self._ticker(record.ticker)
            t.freeze = "frozen" if record.event == "freeze_active" else record.event
            t.ceil = record.ceil

        elif isinstance(record, ParsedWallet):
            if record.ticker is not None and record.balance is not None:
                self.wallets_coin[(record.agent, record.ticker)] = record.balance
            else:
                self.wallets_fiat[record.agent] = record.fiat

        elif isinstance(record, ParsedLeaderboard):
            self.leaderboard = record.ranks

        elif isinstance(record, ParsedSeepnews):
            self.seepnews.append(record)
            self.agents_seen.add(record.agent)

        elif isinstance(record, ParsedTrade):
            self.trades.append(record)
            self.agents_seen.add(record.agent)
            side = record.side.lower()
            coin_key = (record.agent, record.ticker)
            if side == "buy":
                self.wallets_fiat[record.agent] = self.wallets_fiat.get(record.agent, 0.0) - record.fiat
                self.wallets_coin[coin_key] = self.wallets_coin.get(coin_key, 0.0) + record.coins
            elif side == "sell":
                self.wallets_fiat[record.agent] = self.wallets_fiat.get(record.agent, 0.0) + record.fiat
                self.wallets_coin[coin_key] = max(0.0, self.wallets_coin.get(coin_key, 0.0) - record.coins)

        elif isinstance(record, ParsedPostFreezeOrder):
            self.pfos[record.order_id] = record

        elif isinstance(record, ParsedError):
            self.errors.append(record)

        elif isinstance(record, ParsedBlock):
            self.last_block = record

        elif isinstance(record, ParsedAgent):
            self.agents_seen.add(record.agent)

        elif isinstance(record, ParsedAICoinLaunch):
            self._ticker(record.ticker).coin_id = record.coin_id

        # ParsedHeader / ParsedMeta carry no per-entity state worth caching.

    def apply_many(self, records: list[STPRecord]) -> None:
        for record in records:
            self.apply(record)

    # -- convenience accessors --------------------------------------------

    def price(self, ticker: str) -> float | None:
        t = self.tickers.get(ticker)
        return t.price if t else None

    def is_frozen(self, ticker: str) -> bool:
        t = self.tickers.get(ticker)
        return bool(t and t.freeze == "frozen")

    def coin_id_for(self, ticker: str) -> str | None:
        t = self.tickers.get(ticker)
        return t.coin_id if t and t.coin_id else None

    def recent_seepnews(self, category: str | None = None, limit: int = 20) -> list[ParsedSeepnews]:
        items = self.seepnews if category is None else [p for p in self.seepnews if p.category == category]
        return items[-limit:]

    def coin_balance(self, agent_id: str, ticker: str) -> float:
        return self.wallets_coin.get((agent_id, ticker), 0.0)

    def fiat_balance(self, agent_id: str) -> float:
        return self.wallets_fiat.get(agent_id, 0.0)
