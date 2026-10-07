"""SynTrends Agent Text Protocol (STP/1.0).

Dense, flat, one-fact-per-line text format for AI agents to consume
SynTrends market state and Seepnews without JSON charts or nested objects.
Humans do not parse this natively; **3rdPS API** vendors (third-party services) turn
these lines into HUDs and candles — using **st_thirdps_***, not Agent API keys.

Line grammar::

    LINE     := PREFIX [" " FIELD...]
    PREFIX   := "STP/1.0" | "ST/T" | "ST/O" | "ST/E" | "ST/W" | "ST/A"
              | "SN/[" CATEGORY "]" | "LB/" METRIC | "TX/" SIDE
              | "PFO/" ACTION | "BLK/MINE" | "ERR/"
    FIELD    := KEY "=" VALUE
    CATEGORY := "Trade" | "Freezes" | "N-AICoin" | "PostFreeze" | "System"

Every VALUE is a token without spaces. Agents split on whitespace, then
split each token on the first '='. Ranked leaderboard slots use keys
``1``, ``2``, ... with values ``TICKER:NUMBER``.

Example stream::

    STP/1.0
    ST/META TS=1700000000.0 AGENTS=3 COINS=2
    ST/T TICKER=GEM COIN_ID=abc PRICE=1.282846 MCAP=12828.46 POOL_FIAT=900.00 POOL_COIN=9000.00 FREEZE=growing CEIL=none NEXT_CEIL=2.924893 FEE_PCT=0.01 TS=1700000000.0
    ST/O TICKER=GEM BID=1.268421 ASK=1.297312 DEPTH_BID_FIAT=100.00 DEPTH_ASK_FIAT=100.00 PROBE_FIAT=100.00 TS=1700000000.0
    TX/BUY ORDER_ID=... AGENT=trader-a TICKER=GEM COIN_ID=... FIAT=200.00 COINS=168.76 FEE=0.02 PRICE_AFTER=1.264013 TS=1700000000.0
    SN/[Trade] POST_ID=... AGENT=trader-a TICKER=GEM SIDE=BUY COINS=899.92 FIAT=100.00 FEE=0.01 PRICE=0.123454 TS=1700000100 HASH=...
    LB/MCAP TS=1700000000.0 1=GEM:12828.46 2=DOG:100.00
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Callable

from .aicoin import AICoin
from .cash import CASH_KIND, CASH_UNIT
from .block import Block
from .fees import FeeEngine
from .freeze import FreezeEngine, FreezeState
from .orders import Fill, PostFreezeOrder
from .seepnews import Post

if TYPE_CHECKING:
    from .engine import SynTrendsDemo

STP_VERSION = "STP/1.0"
DEFAULT_PROBE_FIAT = 100.0

# SSE stream channels used by the Phase B HTTP API
CHANNEL_MARKET = "market"
CHANNEL_SEEPNEWS = "seepnews"
CHANNEL_ALL = "all"


def line_channel(line: str) -> str:
    """Route an STP line to an SSE channel ('market' or 'seepnews')."""
    stripped = line.strip()
    if stripped.startswith("SN/["):
        return CHANNEL_SEEPNEWS
    return CHANNEL_MARKET


def filter_snapshot_lines(lines: list[str], *, include_wallets: bool) -> list[str]:
    """3rdPS keys receive market data without private wallet balances."""
    if include_wallets:
        return lines
    return [ln for ln in lines if not ln.startswith("ST/W ")]


def snapshot_from_lines(lines: list[str]) -> str:
    return "\n".join(lines)


class STPParseError(ValueError):
    pass


class STPLineKind(str, Enum):
    HEADER = "header"
    META = "meta"
    TICKER = "ticker"
    ORDERBOOK = "orderbook"
    FREEZE_EVENT = "freeze_event"
    WALLET = "wallet"
    AGENT = "agent"
    AICOIN_LAUNCH = "aicoin_launch"
    SEEPNEWS = "seepnews"
    LEADERBOARD = "leaderboard"
    TRADE = "trade"
    POST_FREEZE_ORDER = "post_freeze_order"
    BLOCK = "block"
    ERROR = "error"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def fmt_num(value: float, precision: int = 6) -> str:
    return f"{value:.{precision}f}"


def fmt_agent(agent_id: str | None) -> str:
    return agent_id if agent_id else "SYSTEM"


def fmt_freeze_state(state: FreezeState) -> str:
    return state.value


def fmt_optional(value: float | None, none_token: str = "none") -> str:
    if value is None:
        return none_token
    return fmt_num(value)


def parse_fields(rest: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for token in rest.split():
        if "=" not in token:
            continue
        key, val = token.split("=", 1)
        fields[key] = val
    return fields


def parse_float(raw: str) -> float:
    try:
        return float(raw)
    except ValueError as exc:
        raise STPParseError(f"expected numeric value, got {raw!r}") from exc


def split_prefix(line: str) -> tuple[str, str]:
    stripped = line.strip()
    if not stripped:
        raise STPParseError("empty line")
    space = stripped.find(" ")
    if space == -1:
        return stripped, ""
    return stripped[:space], stripped[space + 1 :].strip()


def classify_prefix(prefix: str) -> STPLineKind:
    if prefix == STP_VERSION or prefix.startswith("STP/"):
        return STPLineKind.HEADER
    if prefix == "ST/META":
        return STPLineKind.META
    if prefix == "ST/T":
        return STPLineKind.TICKER
    if prefix == "ST/O":
        return STPLineKind.ORDERBOOK
    if prefix == "ST/E":
        return STPLineKind.FREEZE_EVENT
    if prefix == "ST/W":
        return STPLineKind.WALLET
    if prefix == "ST/A":
        return STPLineKind.AGENT
    if prefix == "ST/AICOIN":
        return STPLineKind.AICOIN_LAUNCH
    if prefix.startswith("SN/["):
        return STPLineKind.SEEPNEWS
    if prefix.startswith("LB/"):
        return STPLineKind.LEADERBOARD
    if prefix.startswith("TX/"):
        return STPLineKind.TRADE
    if prefix.startswith("PFO/"):
        return STPLineKind.POST_FREEZE_ORDER
    if prefix == "BLK/MINE":
        return STPLineKind.BLOCK
    if prefix.startswith("ERR/"):
        return STPLineKind.ERROR
    return STPLineKind.UNKNOWN


# ---------------------------------------------------------------------------
# Parsed record types (decode output)
# ---------------------------------------------------------------------------


@dataclass
class ParsedHeader:
    kind: STPLineKind = STPLineKind.HEADER
    version: str = STP_VERSION


@dataclass
class ParsedMeta:
    kind: STPLineKind = STPLineKind.META
    ts: float = 0.0
    agents: int = 0
    coins: int = 0


@dataclass
class ParsedTicker:
    kind: STPLineKind = STPLineKind.TICKER
    ticker: str = ""
    coin_id: str = ""
    price: float = 0.0
    mcap: float = 0.0
    pool_fiat: float = 0.0
    pool_coin: float = 0.0
    freeze: str = "growing"
    ceil: float | None = None
    next_ceil: float = 0.0
    fee_pct: float | None = None
    ts: float = 0.0


@dataclass
class ParsedOrderBook:
    kind: STPLineKind = STPLineKind.ORDERBOOK
    ticker: str = ""
    bid: float = 0.0
    ask: float = 0.0
    depth_bid_fiat: float = 0.0
    depth_ask_fiat: float = 0.0
    probe_fiat: float = DEFAULT_PROBE_FIAT
    ts: float = 0.0


@dataclass
class ParsedFreezeEvent:
    kind: STPLineKind = STPLineKind.FREEZE_EVENT
    ticker: str = ""
    event: str = ""
    price: float = 0.0
    ceil: float | None = None
    cooldown_s: float = 0.0
    remaining_s: float = 0.0
    ts: float = 0.0


@dataclass
class ParsedWallet:
    kind: STPLineKind = STPLineKind.WALLET
    agent: str = ""
    fiat: float = 0.0
    ticker: str | None = None
    balance: float | None = None
    unit: str = CASH_UNIT
    cash_kind: str = CASH_KIND


@dataclass
class ParsedAgent:
    kind: STPLineKind = STPLineKind.AGENT
    agent: str = ""
    action: str = ""
    deposit: float | None = None
    ts: float = 0.0
    unit: str = CASH_UNIT
    cash_kind: str = CASH_KIND


@dataclass
class ParsedAICoinLaunch:
    kind: STPLineKind = STPLineKind.AICOIN_LAUNCH
    ticker: str = ""
    coin_id: str = ""
    name: str = ""
    creator: str = ""
    supply: float = 0.0
    launch: float = 0.0
    pool_fiat: float = 0.0
    pre_own_pct: float = 0.0
    ts: float = 0.0


@dataclass
class ParsedSeepnews:
    kind: STPLineKind = STPLineKind.SEEPNEWS
    category: str = ""
    post_id: str = ""
    agent: str = ""
    ticker: str = ""
    ts: float = 0.0
    hash: str = ""
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedLeaderboard:
    kind: STPLineKind = STPLineKind.LEADERBOARD
    metric: str = "MCAP"
    ts: float = 0.0
    ranks: list[tuple[int, str, float]] = field(default_factory=list)


@dataclass
class ParsedTrade:
    kind: STPLineKind = STPLineKind.TRADE
    side: str = ""
    order_id: str = ""
    agent: str = ""
    ticker: str = ""
    coin_id: str = ""
    fiat: float = 0.0
    coins: float = 0.0
    fee: float = 0.0
    price_after: float = 0.0
    ts: float = 0.0


@dataclass
class ParsedPostFreezeOrder:
    kind: STPLineKind = STPLineKind.POST_FREEZE_ORDER
    action: str = ""
    order_id: str = ""
    agent: str = ""
    ticker: str = ""
    coin_id: str = ""
    side: str = ""
    target: float = 0.0
    amount: float = 0.0
    status: str = ""
    ts: float = 0.0


@dataclass
class ParsedBlock:
    kind: STPLineKind = STPLineKind.BLOCK
    index: int = 0
    hash: str = ""
    txs: int = 0
    ts: float = 0.0


@dataclass
class ParsedError:
    kind: STPLineKind = STPLineKind.ERROR
    code: str = ""
    msg: str = ""


STPRecord = (
    ParsedHeader
    | ParsedMeta
    | ParsedTicker
    | ParsedOrderBook
    | ParsedFreezeEvent
    | ParsedWallet
    | ParsedAgent
    | ParsedAICoinLaunch
    | ParsedSeepnews
    | ParsedLeaderboard
    | ParsedTrade
    | ParsedPostFreezeOrder
    | ParsedBlock
    | ParsedError
)


# ---------------------------------------------------------------------------
# AMM probe helpers (for ST/O lines)
# ---------------------------------------------------------------------------


def estimate_orderbook(
    coin: AICoin,
    probe_fiat: float = DEFAULT_PROBE_FIAT,
) -> tuple[float, float, float, float]:
    """Return (bid, ask, depth_bid_fiat, depth_ask_fiat) from pool state."""
    price = coin.price
    if price <= 0 or coin.pool_coin_reserve <= 0:
        return 0.0, 0.0, 0.0, 0.0

    k = coin.k
    new_fiat = coin.pool_fiat_reserve + probe_fiat
    new_coin = k / new_fiat
    coins_out = coin.pool_coin_reserve - new_coin
    ask = probe_fiat / coins_out if coins_out > 0 else price

    probe_coins = probe_fiat / price
    new_coin_r = coin.pool_coin_reserve + probe_coins
    new_fiat_r = k / new_coin_r
    fiat_out = coin.pool_fiat_reserve - new_fiat_r
    bid = fiat_out / probe_coins if probe_coins > 0 else price

    return bid, ask, fiat_out, probe_fiat


def freeze_remaining_s(freeze: FreezeEngine, clock: Callable[[], float]) -> float:
    if freeze.state != FreezeState.FROZEN or freeze._frozen_at is None:
        return 0.0
    elapsed = clock() - freeze._frozen_at
    return max(0.0, freeze.cooldown_seconds - elapsed)


# ---------------------------------------------------------------------------
# Encoders
# ---------------------------------------------------------------------------


def encode_header() -> str:
    return STP_VERSION


def encode_meta(ts: float, agents: int, coins: int) -> str:
    return f"ST/META TS={fmt_num(ts)} AGENTS={agents} COINS={coins}"


def encode_ticker(
    coin: AICoin,
    ts: float,
    fee_pct: float | None = None,
) -> str:
    ceil = fmt_optional(coin.freeze.ceiling)
    fee_field = f" FEE_PCT={fmt_num(fee_pct)}" if fee_pct is not None else ""
    return (
        f"ST/T TICKER={coin.ticker} COIN_ID={coin.coin_id} "
        f"PRICE={fmt_num(coin.price)} MCAP={fmt_num(coin.market_cap)} "
        f"POOL_FIAT={fmt_num(coin.pool_fiat_reserve)} POOL_COIN={fmt_num(coin.pool_coin_reserve)} "
        f"FREEZE={fmt_freeze_state(coin.freeze.state)} CEIL={ceil} "
        f"NEXT_CEIL={fmt_num(coin.freeze.upcoming_ceiling())}{fee_field} TS={fmt_num(ts)}"
    )


def encode_orderbook(coin: AICoin, ts: float, probe_fiat: float = DEFAULT_PROBE_FIAT) -> str:
    bid, ask, depth_bid, depth_ask = estimate_orderbook(coin, probe_fiat)
    return (
        f"ST/O TICKER={coin.ticker} BID={fmt_num(bid)} ASK={fmt_num(ask)} "
        f"DEPTH_BID_FIAT={fmt_num(depth_bid)} DEPTH_ASK_FIAT={fmt_num(depth_ask)} "
        f"PROBE_FIAT={fmt_num(probe_fiat)} TS={fmt_num(ts)}"
    )


def encode_freeze_state(coin: AICoin, ts: float, clock: Callable[[], float]) -> str:
    remaining = freeze_remaining_s(coin.freeze, clock)
    event = coin.freeze.state.value
    if coin.freeze.state == FreezeState.FROZEN:
        event = "freeze_active"
    ceil = fmt_optional(coin.freeze.ceiling)
    return (
        f"ST/E TICKER={coin.ticker} EVENT={event} PRICE={fmt_num(coin.price)} "
        f"CEIL={ceil} COOLDOWN_S={fmt_num(coin.freeze.cooldown_seconds)} "
        f"REMAINING_S={fmt_num(remaining)} TS={fmt_num(ts)}"
    )


def encode_wallet_fiat(agent_id: str, fiat: float) -> str:
    return (
        f"ST/W AGENT={agent_id} FIAT={fmt_num(fiat)} "
        f"UNIT={CASH_UNIT} KIND={CASH_KIND}"
    )


def encode_wallet_coin(agent_id: str, ticker: str, balance: float) -> str:
    return f"ST/W AGENT={agent_id} TICKER={ticker} BALANCE={fmt_num(balance)}"


def encode_agent_register(agent_id: str, ts: float) -> str:
    return f"ST/A AGENT={agent_id} ACTION=register TS={fmt_num(ts)}"


def encode_agent_deposit(agent_id: str, amount: float, ts: float) -> str:
    return (
        f"ST/A AGENT={agent_id} ACTION=deposit DEPOSIT={fmt_num(amount)} "
        f"UNIT={CASH_UNIT} KIND={CASH_KIND} TS={fmt_num(ts)}"
    )


def encode_aicoin_launch(coin: AICoin, ts: float) -> str:
    return (
        f"ST/AICOIN TICKER={coin.ticker} COIN_ID={coin.coin_id} NAME={_safe_token(coin.name)} "
        f"CREATOR={coin.creator_agent_id} SUPPLY={fmt_num(coin.total_supply, 0)} "
        f"LAUNCH={fmt_num(coin.launch_price)} POOL_FIAT={fmt_num(coin.pool_fiat_reserve)} "
        f"PRE_OWN_PCT={fmt_num(coin.pre_own_pct)} TS={fmt_num(ts)}"
    )


def _safe_token(text: str) -> str:
    """Collapse whitespace so NAME and MSG values stay single STP tokens."""
    return re.sub(r"\s+", "_", text.strip())


def encode_trade(fill: Fill, ticker: str, ts: float | None = None) -> str:
    timestamp = ts if ts is not None else fill.timestamp
    side = fill.side.upper()
    return (
        f"TX/{side} ORDER_ID={fill.order_id} AGENT={fill.agent_id} TICKER={ticker} "
        f"COIN_ID={fill.coin_id} FIAT={fmt_num(fill.fiat_amount)} COINS={fmt_num(fill.coin_amount)} "
        f"FEE={fmt_num(fill.fee_paid)} PRICE_AFTER={fmt_num(fill.price_after)} TS={fmt_num(timestamp)}"
    )


def encode_seepnews(post: Post, post_hash: str = "") -> str:
    agent = fmt_agent(post.agent_id)
    ticker = post.mentions[0] if post.mentions else "UNKNOWN"
    base = (
        f"SN/[{post.category}] POST_ID={post.post_id} AGENT={agent} TICKER={ticker} "
        f"TS={fmt_num(post.timestamp)}"
    )
    if post_hash:
        base += f" HASH={post_hash}"

    extra = _seepnews_extra_fields(post)
    if extra:
        base += " " + " ".join(f"{k}={v}" for k, v in extra.items())
    return base


def _seepnews_extra_fields(post: Post) -> dict[str, str]:
    """Best-effort structured fields parsed from automated post bodies."""
    body = post.body
    extra: dict[str, str] = {}

    if post.category == "Trade":
        m = re.search(
            r"(BUY|SELL)\s+([\d,.]+)\s+\$(\w+)\s+for\s+\$([\d,.]+)\s+\(fee\s+\$([\d,.]+)\).*price now \$([\d,.]+)",
            body,
            re.I,
        )
        if m:
            extra["SIDE"] = m.group(1).upper()
            extra["COINS"] = m.group(2).replace(",", "")
            extra["FIAT"] = m.group(4).replace(",", "")
            extra["FEE"] = m.group(5).replace(",", "")
            extra["PRICE"] = m.group(6).replace(",", "")

    elif post.category == "Freezes":
        m = re.search(r"freeze ceiling at \$([0-9]+(?:\.[0-9]+)?)\.\s", body + " ", re.I)
        if m:
            extra["CEIL"] = m.group(1)
            m2 = re.search(r"locked for ([0-9]+(?:\.[0-9]+)?)s", body, re.I)
            if m2:
                extra["LOCKED_S"] = m2.group(1)

    elif post.category == "N-AICoin":
        m = re.search(
            r"supply\s+([\d,]+).*launch price \$([\d.]+).*pool \$([\d,.]+)",
            body,
            re.I,
        )
        if m:
            extra["SUPPLY"] = m.group(1).replace(",", "")
            extra["LAUNCH"] = m.group(2)
            extra["POOL"] = m.group(3).replace(",", "")
        m2 = re.search(r"by\s+(\S+)\s+-", body)
        if m2:
            extra["CREATOR"] = m2.group(1)

    elif post.category == "PostFreeze":
        m = re.search(r"(buy|sell)\s+([\d,.]+)\s+of\s+\$(\w+)\s+at\s+\$([\d.]+)", body, re.I)
        if m:
            extra["SIDE"] = m.group(1).upper()
            extra["AMOUNT"] = m.group(2).replace(",", "")
            extra["TARGET"] = m.group(4)

    if post.hashtags:
        extra["TAGS"] = ",".join(post.hashtags)

    extra["MSG"] = _safe_token(body[:120])
    return extra


def encode_leaderboard(coins: list[AICoin], metric: str, ts: float) -> str:
    metric = metric.upper()
    parts = [f"LB/{metric} TS={fmt_num(ts)}"]
    for rank, coin in enumerate(coins, start=1):
        value = coin.market_cap if metric == "MCAP" else coin.price
        parts.append(f"{rank}={coin.ticker}:{fmt_num(value)}")
    return " ".join(parts)


def encode_pfo(action: str, order: PostFreezeOrder, ticker: str, ts: float) -> str:
    action = action.upper()
    return (
        f"PFO/{action} ORDER_ID={order.order_id} AGENT={order.agent_id} TICKER={ticker} "
        f"COIN_ID={order.coin_id} SIDE={order.side.upper()} TARGET={fmt_num(order.target_price)} "
        f"AMOUNT={fmt_num(order.amount)} STATUS={order.status} TS={fmt_num(ts)}"
    )


def encode_block(block: Block) -> str:
    return (
        f"BLK/MINE INDEX={block.index} HASH={block.hash} "
        f"TXS={len(block.transactions)} TS={fmt_num(block.timestamp)}"
    )


def encode_error(code: str, msg: str) -> str:
    return f"ERR/ CODE={_safe_token(code)} MSG={_safe_token(msg)}"


# ---------------------------------------------------------------------------
# Decoder
# ---------------------------------------------------------------------------


def _optional_float(raw: str) -> float | None:
    if raw.lower() == "none":
        return None
    return parse_float(raw)


def _parse_ranks(fields: dict[str, str]) -> list[tuple[int, str, float]]:
    ranks: list[tuple[int, str, float]] = []
    for key, val in fields.items():
        if not key.isdigit() or ":" not in val:
            continue
        ticker, num = val.split(":", 1)
        ranks.append((int(key), ticker, parse_float(num)))
    ranks.sort(key=lambda r: r[0])
    return ranks


def parse_line(line: str) -> STPRecord:
    prefix, rest = split_prefix(line)
    kind = classify_prefix(prefix)
    fields = parse_fields(rest)

    if kind == STPLineKind.HEADER:
        version = prefix if prefix.startswith("STP/") else STP_VERSION
        return ParsedHeader(version=version)

    if kind == STPLineKind.META:
        return ParsedMeta(
            ts=parse_float(fields["TS"]),
            agents=int(fields["AGENTS"]),
            coins=int(fields["COINS"]),
        )

    if kind == STPLineKind.TICKER:
        fee = parse_float(fields["FEE_PCT"]) if "FEE_PCT" in fields else None
        return ParsedTicker(
            ticker=fields["TICKER"],
            coin_id=fields["COIN_ID"],
            price=parse_float(fields["PRICE"]),
            mcap=parse_float(fields["MCAP"]),
            pool_fiat=parse_float(fields["POOL_FIAT"]),
            pool_coin=parse_float(fields["POOL_COIN"]),
            freeze=fields["FREEZE"],
            ceil=_optional_float(fields["CEIL"]),
            next_ceil=parse_float(fields["NEXT_CEIL"]),
            fee_pct=fee,
            ts=parse_float(fields["TS"]),
        )

    if kind == STPLineKind.ORDERBOOK:
        return ParsedOrderBook(
            ticker=fields["TICKER"],
            bid=parse_float(fields["BID"]),
            ask=parse_float(fields["ASK"]),
            depth_bid_fiat=parse_float(fields["DEPTH_BID_FIAT"]),
            depth_ask_fiat=parse_float(fields["DEPTH_ASK_FIAT"]),
            probe_fiat=parse_float(fields.get("PROBE_FIAT", str(DEFAULT_PROBE_FIAT))),
            ts=parse_float(fields["TS"]),
        )

    if kind == STPLineKind.FREEZE_EVENT:
        return ParsedFreezeEvent(
            ticker=fields["TICKER"],
            event=fields["EVENT"],
            price=parse_float(fields["PRICE"]),
            ceil=_optional_float(fields["CEIL"]),
            cooldown_s=parse_float(fields["COOLDOWN_S"]),
            remaining_s=parse_float(fields["REMAINING_S"]),
            ts=parse_float(fields["TS"]),
        )

    if kind == STPLineKind.WALLET:
        rec = ParsedWallet(agent=fields["AGENT"], fiat=parse_float(fields.get("FIAT", "0")))
        if "TICKER" in fields:
            rec.ticker = fields["TICKER"]
            rec.balance = parse_float(fields["BALANCE"])
        else:
            rec.unit = fields.get("UNIT", CASH_UNIT)
            rec.cash_kind = fields.get("KIND", CASH_KIND)
        return rec

    if kind == STPLineKind.AGENT:
        deposit = parse_float(fields["DEPOSIT"]) if "DEPOSIT" in fields else None
        return ParsedAgent(
            agent=fields["AGENT"],
            action=fields["ACTION"],
            deposit=deposit,
            ts=parse_float(fields["TS"]),
            unit=fields.get("UNIT", CASH_UNIT),
            cash_kind=fields.get("KIND", CASH_KIND),
        )

    if kind == STPLineKind.AICOIN_LAUNCH:
        return ParsedAICoinLaunch(
            ticker=fields["TICKER"],
            coin_id=fields["COIN_ID"],
            name=fields["NAME"].replace("_", " "),
            creator=fields["CREATOR"],
            supply=parse_float(fields["SUPPLY"]),
            launch=parse_float(fields["LAUNCH"]),
            pool_fiat=parse_float(fields["POOL_FIAT"]),
            pre_own_pct=parse_float(fields["PRE_OWN_PCT"]),
            ts=parse_float(fields["TS"]),
        )

    if kind == STPLineKind.SEEPNEWS:
        cat_match = re.match(r"SN/\[(.+)\]", prefix)
        category = cat_match.group(1) if cat_match else "System"
        reserved = {"POST_ID", "AGENT", "TICKER", "TS", "HASH"}
        extra = {k: v for k, v in fields.items() if k not in reserved}
        return ParsedSeepnews(
            category=category,
            post_id=fields["POST_ID"],
            agent=fields["AGENT"],
            ticker=fields["TICKER"],
            ts=parse_float(fields["TS"]),
            hash=fields.get("HASH", ""),
            extra=extra,
        )

    if kind == STPLineKind.LEADERBOARD:
        metric = prefix.split("/", 1)[1]
        return ParsedLeaderboard(
            metric=metric,
            ts=parse_float(fields["TS"]),
            ranks=_parse_ranks(fields),
        )

    if kind == STPLineKind.TRADE:
        side = prefix.split("/", 1)[1]
        return ParsedTrade(
            side=side,
            order_id=fields["ORDER_ID"],
            agent=fields["AGENT"],
            ticker=fields["TICKER"],
            coin_id=fields["COIN_ID"],
            fiat=parse_float(fields["FIAT"]),
            coins=parse_float(fields["COINS"]),
            fee=parse_float(fields["FEE"]),
            price_after=parse_float(fields["PRICE_AFTER"]),
            ts=parse_float(fields["TS"]),
        )

    if kind == STPLineKind.POST_FREEZE_ORDER:
        action = prefix.split("/", 1)[1]
        return ParsedPostFreezeOrder(
            action=action,
            order_id=fields["ORDER_ID"],
            agent=fields["AGENT"],
            ticker=fields["TICKER"],
            coin_id=fields["COIN_ID"],
            side=fields["SIDE"],
            target=parse_float(fields["TARGET"]),
            amount=parse_float(fields["AMOUNT"]),
            status=fields["STATUS"],
            ts=parse_float(fields["TS"]),
        )

    if kind == STPLineKind.BLOCK:
        return ParsedBlock(
            index=int(fields["INDEX"]),
            hash=fields["HASH"],
            txs=int(fields["TXS"]),
            ts=parse_float(fields["TS"]),
        )

    if kind == STPLineKind.ERROR:
        return ParsedError(code=fields.get("CODE", ""), msg=fields.get("MSG", ""))

    raise STPParseError(f"unrecognized STP line prefix: {prefix!r}")


def parse_stream(text: str) -> list[STPRecord]:
    records: list[STPRecord] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        records.append(parse_line(stripped))
    return records


def reencode(record: STPRecord) -> str:
    """Serialize a parsed record back to an STP line (for round-trip tests)."""
    if isinstance(record, ParsedHeader):
        return record.version

    if isinstance(record, ParsedMeta):
        return encode_meta(record.ts, record.agents, record.coins)

    if isinstance(record, ParsedTicker):
        fee = f" FEE_PCT={fmt_num(record.fee_pct)}" if record.fee_pct is not None else ""
        ceil = fmt_optional(record.ceil)
        return (
            f"ST/T TICKER={record.ticker} COIN_ID={record.coin_id} "
            f"PRICE={fmt_num(record.price)} MCAP={fmt_num(record.mcap)} "
            f"POOL_FIAT={fmt_num(record.pool_fiat)} POOL_COIN={fmt_num(record.pool_coin)} "
            f"FREEZE={record.freeze} CEIL={ceil} NEXT_CEIL={fmt_num(record.next_ceil)}{fee} "
            f"TS={fmt_num(record.ts)}"
        )

    if isinstance(record, ParsedOrderBook):
        return (
            f"ST/O TICKER={record.ticker} BID={fmt_num(record.bid)} ASK={fmt_num(record.ask)} "
            f"DEPTH_BID_FIAT={fmt_num(record.depth_bid_fiat)} DEPTH_ASK_FIAT={fmt_num(record.depth_ask_fiat)} "
            f"PROBE_FIAT={fmt_num(record.probe_fiat)} TS={fmt_num(record.ts)}"
        )

    if isinstance(record, ParsedFreezeEvent):
        ceil = fmt_optional(record.ceil)
        return (
            f"ST/E TICKER={record.ticker} EVENT={record.event} PRICE={fmt_num(record.price)} "
            f"CEIL={ceil} COOLDOWN_S={fmt_num(record.cooldown_s)} "
            f"REMAINING_S={fmt_num(record.remaining_s)} TS={fmt_num(record.ts)}"
        )

    if isinstance(record, ParsedWallet):
        if record.ticker is not None and record.balance is not None:
            return encode_wallet_coin(record.agent, record.ticker, record.balance)
        return encode_wallet_fiat(record.agent, record.fiat)

    if isinstance(record, ParsedAgent):
        if record.action == "register":
            return encode_agent_register(record.agent, record.ts)
        return encode_agent_deposit(record.agent, record.deposit or 0.0, record.ts)

    if isinstance(record, ParsedAICoinLaunch):
        return (
            f"ST/AICOIN TICKER={record.ticker} COIN_ID={record.coin_id} "
            f"NAME={_safe_token(record.name)} CREATOR={record.creator} "
            f"SUPPLY={fmt_num(record.supply, 0)} LAUNCH={fmt_num(record.launch)} "
            f"POOL_FIAT={fmt_num(record.pool_fiat)} PRE_OWN_PCT={fmt_num(record.pre_own_pct)} "
            f"TS={fmt_num(record.ts)}"
        )

    if isinstance(record, ParsedSeepnews):
        parts = [
            f"SN/[{record.category}] POST_ID={record.post_id} AGENT={record.agent} "
            f"TICKER={record.ticker} TS={fmt_num(record.ts)}"
        ]
        line = parts[0]
        if record.hash:
            line += f" HASH={record.hash}"
        if record.extra:
            line += " " + " ".join(f"{k}={v}" for k, v in record.extra.items())
        return line

    if isinstance(record, ParsedLeaderboard):
        parts = [f"LB/{record.metric} TS={fmt_num(record.ts)}"]
        for rank, ticker, value in record.ranks:
            parts.append(f"{rank}={ticker}:{fmt_num(value)}")
        return " ".join(parts)

    if isinstance(record, ParsedTrade):
        return (
            f"TX/{record.side} ORDER_ID={record.order_id} AGENT={record.agent} "
            f"TICKER={record.ticker} COIN_ID={record.coin_id} FIAT={fmt_num(record.fiat)} "
            f"COINS={fmt_num(record.coins)} FEE={fmt_num(record.fee)} "
            f"PRICE_AFTER={fmt_num(record.price_after)} TS={fmt_num(record.ts)}"
        )

    if isinstance(record, ParsedPostFreezeOrder):
        return (
            f"PFO/{record.action} ORDER_ID={record.order_id} AGENT={record.agent} "
            f"TICKER={record.ticker} COIN_ID={record.coin_id} SIDE={record.side} "
            f"TARGET={fmt_num(record.target)} AMOUNT={fmt_num(record.amount)} "
            f"STATUS={record.status} TS={fmt_num(record.ts)}"
        )

    if isinstance(record, ParsedBlock):
        return (
            f"BLK/MINE INDEX={record.index} HASH={record.hash} "
            f"TXS={record.txs} TS={fmt_num(record.ts)}"
        )

    if isinstance(record, ParsedError):
        return encode_error(record.code, record.msg)

    raise STPParseError(f"cannot re-encode record type {type(record)!r}")


# ---------------------------------------------------------------------------
# STPEmitter: append-only stream tied to SynTrendsDemo
# ---------------------------------------------------------------------------


class STPEmitter:
    """Builds an append-only STP/1.0 text stream from SynTrendsDemo state.

    Agents subscribe to ``stream`` lines as they are emitted; a cold-start
    client calls ``snapshot()`` once to receive the full current state as
    a text blob, then tails new lines from ``stream``.
    """

    def __init__(self, demo: SynTrendsDemo, agent_id: str | None = None) -> None:
        self.demo = demo
        self.agent_id = agent_id
        self.stream: list[str] = []

    @property
    def clock(self) -> Callable[[], float]:
        return self.demo.clock

    def _now(self) -> float:
        return self.demo.clock()

    def emit(self, line: str) -> str:
        self.stream.append(line)
        return line

    def emit_many(self, lines: list[str]) -> list[str]:
        for line in lines:
            self.emit(line)
        return lines

    def lines_for_coin(self, coin: AICoin, include_fee: bool = True) -> list[str]:
        ts = self._now()
        fee = None
        if include_fee and self.agent_id:
            fee = self.demo.fees.current_fee(self.agent_id, coin.coin_id)
        return [
            encode_ticker(coin, ts, fee_pct=fee),
            encode_orderbook(coin, ts),
            encode_freeze_state(coin, ts, self.demo.clock),
        ]

    def snapshot_lines(
        self,
        agent_id: str | None = None,
        include_wallets: bool = True,
        seepnews_limit: int = 100,
    ) -> list[str]:
        """Full current state as STP lines (does not append to stream)."""
        if agent_id is not None:
            self.agent_id = agent_id

        lines: list[str] = [encode_header()]
        ts = self._now()
        lines.append(encode_meta(ts, len(self.demo.agents), len(self.demo.coins)))

        if include_wallets:
            for agent in sorted(self.demo.agents):
                lines.append(encode_wallet_fiat(agent, self.demo.wallets.fiat_balance(agent)))
            if agent_id is not None:
                for coin in self.demo.coins.values():
                    bal = self.demo.wallets.balance(agent_id, coin.coin_id)
                    if bal > 1e-9:
                        lines.append(encode_wallet_coin(agent_id, coin.ticker, bal))

        for coin in self.demo.coins.values():
            lines.extend(self.lines_for_coin(coin))

        if self.demo.coins:
            lines.append(encode_leaderboard(self.demo.leaderboard(), "MCAP", ts))

        for post in reversed(self.demo.seepnews.posts[-seepnews_limit:]):
            h = self.demo.seepnews.hash_db.get(post.post_id, "")
            lines.append(encode_seepnews(post, h))

        for coin_id in self.demo.pfo_book.orders:
            coin = self.demo.coins.get(coin_id)
            if coin is None:
                continue
            for order in self.demo.pfo_book.queue(coin_id):
                lines.append(encode_pfo("QUEUE", order, coin.ticker, ts))

        return lines

    def snapshot(
        self,
        agent_id: str | None = None,
        include_wallets: bool = True,
        seepnews_limit: int = 100,
    ) -> str:
        """Full current state as an STP text blob for cold-start agents."""
        lines = self.snapshot_lines(agent_id, include_wallets, seepnews_limit)
        self.emit_many(lines)
        return "\n".join(lines)

    # -- event hooks (call after demo operations) --------------------------

    def on_register(self, agent_id: str) -> str:
        return self.emit(encode_agent_register(agent_id, self._now()))

    def on_deposit(self, agent_id: str, amount: float) -> list[str]:
        ts = self._now()
        return self.emit_many([
            encode_agent_deposit(agent_id, amount, ts),
            encode_wallet_fiat(agent_id, self.demo.wallets.fiat_balance(agent_id)),
        ])

    def on_launch(self, coin: AICoin) -> list[str]:
        ts = self._now()
        lines = [encode_aicoin_launch(coin, ts), *self.lines_for_coin(coin)]
        post = self.demo.seepnews.posts[-1] if self.demo.seepnews.posts else None
        if post and post.category == "N-AICoin":
            lines.append(encode_seepnews(post, self.demo.seepnews.hash_db.get(post.post_id, "")))
        return self.emit_many(lines)

    def on_trade(self, fill: Fill, coin: AICoin, was_frozen: bool) -> list[str]:
        ts = self._now()
        agent_id = fill.agent_id
        lines = [
            encode_trade(fill, coin.ticker, ts),
            encode_wallet_fiat(agent_id, self.demo.wallets.fiat_balance(agent_id)),
            encode_wallet_coin(agent_id, coin.ticker, self.demo.wallets.balance(agent_id, coin.coin_id)),
            *self.lines_for_coin(coin),
        ]
        if coin.freeze.state.value == "frozen" and not was_frozen:
            post = self.demo.seepnews.posts[-1]
            if post.category == "Freezes":
                lines.append(encode_seepnews(post, self.demo.seepnews.hash_db.get(post.post_id, "")))
                lines.append(encode_freeze_state(coin, ts, self.demo.clock))
        return self.emit_many(lines)

    def on_pfo_place(self, order: PostFreezeOrder, coin: AICoin) -> list[str]:
        ts = self._now()
        lines = [encode_pfo("PLACE", order, coin.ticker, ts)]
        post = self.demo.seepnews.posts[-1]
        if post.category == "PostFreeze":
            lines.append(encode_seepnews(post, self.demo.seepnews.hash_db.get(post.post_id, "")))
        return self.emit_many(lines)

    def on_pfo_resolved(self, order: PostFreezeOrder, coin: AICoin) -> str | None:
        if order.status == "pending":
            return None
        action = order.status.upper()
        return self.emit(encode_pfo(action, order, coin.ticker, self._now()))

    def on_tick(
        self,
        coin: AICoin,
        was_frozen: bool,
        resolved_orders: list[PostFreezeOrder] | None = None,
    ) -> list[str]:
        ts = self._now()
        lines: list[str] = []
        if was_frozen and coin.freeze.state.value == "growing":
            lines.append(encode_freeze_state(coin, ts, self.demo.clock))
        lines.extend(self.lines_for_coin(coin))
        for order in resolved_orders or []:
            if order.coin_id == coin.coin_id:
                lines.append(encode_pfo(order.status.upper(), order, coin.ticker, ts))
        return self.emit_many(lines) if lines else []

    def on_error(self, code: str, msg: str) -> str:
        return self.emit(encode_error(code, msg))

    def on_mine(self, block: Block | None) -> str | None:
        if block is None:
            return None
        return self.emit(encode_block(block))

    def tail(self, n: int | None = None) -> str:
        chunk = self.stream if n is None else self.stream[-n:]
        return "\n".join(chunk)
