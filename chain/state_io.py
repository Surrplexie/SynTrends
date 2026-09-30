"""Serialize / deserialize SynTrendsDemo + ManualClock for Phase E persistence."""

from __future__ import annotations

from typing import Any, Callable

from .aicoin import AICoin
from .block import Block, SynTrendsChain, Transaction
from .clock import ManualClock
from .engine import SynTrendsDemo
from .fees import FeeEngine, _FeeState
from .freeze import FreezeEngine, FreezeState
from .orders import PostFreezeOrder, PostFreezeOrderBook, TradingEngine
from .seepnews import Post, Seepnews
from .wallet import WalletRegistry


def _freeze_to_dict(fe: FreezeEngine) -> dict[str, Any]:
    return {
        "start_price": fe.start_price,
        "cooldown_seconds": fe.cooldown_seconds,
        "state": fe.state.value,
        "ceiling": fe.ceiling,
        "has_frozen_once": fe.has_frozen_once,
        "freeze_history": list(fe.freeze_history),
        "frozen_at": fe._frozen_at,
        "watch_low": fe._watch_low,
    }


def _freeze_from_dict(data: dict[str, Any], clock: Callable[[], float]) -> FreezeEngine:
    fe = FreezeEngine(
        start_price=data["start_price"],
        cooldown_seconds=data["cooldown_seconds"],
        clock=clock,
    )
    fe.state = FreezeState(data["state"])
    fe.ceiling = data.get("ceiling")
    fe.has_frozen_once = data.get("has_frozen_once", False)
    fe.freeze_history = list(data.get("freeze_history", []))
    fe._frozen_at = data.get("frozen_at")
    fe._watch_low = data.get("watch_low")
    return fe


def _coin_to_dict(coin: AICoin) -> dict[str, Any]:
    return {
        "coin_id": coin.coin_id,
        "ticker": coin.ticker,
        "name": coin.name,
        "creator_agent_id": coin.creator_agent_id,
        "total_supply": coin.total_supply,
        "pre_own_pct": coin.pre_own_pct,
        "mint_enabled": coin.mint_enabled,
        "is_corporate": coin.is_corporate,
        "launch_price": coin.launch_price,
        "pool_coin_reserve": coin.pool_coin_reserve,
        "pool_fiat_reserve": coin.pool_fiat_reserve,
        "creator_coins": coin.creator_coins,
        "created_at": coin.created_at,
        "freeze": _freeze_to_dict(coin.freeze),
    }


def _coin_from_dict(data: dict[str, Any], clock: Callable[[], float]) -> AICoin:
    return AICoin(
        coin_id=data["coin_id"],
        ticker=data["ticker"],
        name=data["name"],
        creator_agent_id=data["creator_agent_id"],
        total_supply=data["total_supply"],
        pre_own_pct=data["pre_own_pct"],
        mint_enabled=data.get("mint_enabled", False),
        is_corporate=data.get("is_corporate", False),
        launch_price=data["launch_price"],
        pool_coin_reserve=data["pool_coin_reserve"],
        pool_fiat_reserve=data["pool_fiat_reserve"],
        creator_coins=data["creator_coins"],
        freeze=_freeze_from_dict(data["freeze"], clock),
        created_at=data.get("created_at", clock()),
    )


def dump_demo(demo: SynTrendsDemo, clock: ManualClock) -> dict[str, Any]:
    wallets = demo.wallets
    wallet_map = {f"{a}|{c}": addr for (a, c), addr in wallets._wallets.items()}

    fees_state = {
        f"{a}|{c}": {"percent": s.percent, "last_update": s.last_update}
        for (a, c), s in demo.fees._state.items()
    }

    pfo_orders: list[dict[str, Any]] = []
    for book in demo.pfo_book.orders.values():
        for order in book.values():
            pfo_orders.append({
                "order_id": order.order_id,
                "agent_id": order.agent_id,
                "coin_id": order.coin_id,
                "side": order.side,
                "target_price": order.target_price,
                "amount": order.amount,
                "placed_at": order.placed_at,
                "filled_amount": order.filled_amount,
                "status": order.status,
            })

    posts = [
        {
            "post_id": p.post_id,
            "agent_id": p.agent_id,
            "category": p.category,
            "body": p.body,
            "mentions": p.mentions,
            "hashtags": p.hashtags,
            "timestamp": p.timestamp,
        }
        for p in demo.seepnews.posts
    ]

    blocks = [
        {
            "index": block.index,
            "timestamp": block.timestamp,
            "previous_hash": block.previous_hash,
            "nonce": block.nonce,
            "hash": block.hash,
            "transactions": [t.to_dict() for t in block.transactions],
        }
        for block in demo.chain.chain
    ]

    return {
        "version": 1,
        "clock_time": clock(),
        "config": {
            "cooldown_seconds": demo._default_cooldown,
            "pfo_timeout_seconds": demo.pfo_book.timeout_seconds,
            "seepnews_cooldown_seconds": demo.seepnews.cooldown_seconds,
        },
        "agents": sorted(demo.agents),
        "coins": [_coin_to_dict(c) for c in demo.coins.values()],
        "wallets": {
            "wallet_map": wallet_map,
            "coin_balances": dict(wallets._coin_balances),
            "fiat_balances": dict(wallets._fiat_balances),
        },
        "fees": fees_state,
        "pfo_orders": pfo_orders,
        "seepnews": {
            "posts": posts,
            "hash_db": dict(demo.seepnews.hash_db),
            "last_post_at": dict(demo.seepnews._last_post_at),
            "body_locks": {
                fp: {"origin": origin, "expires": exp}
                for fp, (origin, exp) in demo.seepnews._body_locks.items()
            },
            "retention_seconds": demo.seepnews.retention_seconds,
        },
        "chain": {
            "blocks": blocks,
            "pending": [t.to_dict() for t in demo.chain.pending],
        },
    }


def load_demo(data: dict[str, Any], clock: ManualClock) -> SynTrendsDemo:
    cfg = data.get("config", {})
    target_time = data.get("clock_time", clock())
    if target_time > clock():
        clock.advance(target_time - clock())

    demo = SynTrendsDemo(
        cooldown_seconds=cfg.get("cooldown_seconds", 10.0),
        pfo_timeout_seconds=cfg.get("pfo_timeout_seconds", 15.0),
        seepnews_cooldown_seconds=cfg.get("seepnews_cooldown_seconds", 0.0),
        clock=clock,
    )

    demo.agents = set(data.get("agents", []))
    for coin_data in data.get("coins", []):
        coin = _coin_from_dict(coin_data, clock)
        demo.coins[coin.coin_id] = coin

    w = data.get("wallets", {})
    demo.wallets = WalletRegistry()
    demo.wallets._wallets = {}
    for key, addr in w.get("wallet_map", {}).items():
        agent_id, coin_id = key.split("|", 1)
        demo.wallets._wallets[(agent_id, coin_id)] = addr
    demo.wallets._coin_balances = dict(w.get("coin_balances", {}))
    demo.wallets._fiat_balances = dict(w.get("fiat_balances", {}))

    demo.fees = FeeEngine(clock=clock)
    for key, st in data.get("fees", {}).items():
        agent_id, coin_id = key.split("|", 1)
        demo.fees._state[(agent_id, coin_id)] = _FeeState(st["percent"], st["last_update"])

    demo.pfo_book = PostFreezeOrderBook(timeout_seconds=cfg.get("pfo_timeout_seconds", 15.0), clock=clock)
    for od in data.get("pfo_orders", []):
        order = PostFreezeOrder(
            order_id=od["order_id"],
            agent_id=od["agent_id"],
            coin_id=od["coin_id"],
            side=od["side"],
            target_price=od["target_price"],
            amount=od["amount"],
            placed_at=od["placed_at"],
            filled_amount=od.get("filled_amount", 0.0),
            status=od.get("status", "pending"),
        )
        demo.pfo_book.orders.setdefault(order.coin_id, {})[order.agent_id] = order

    sn = data.get("seepnews", {})
    demo.seepnews = Seepnews(
        cooldown_seconds=cfg.get("seepnews_cooldown_seconds", 0.0),
        retention_seconds=sn.get("retention_seconds", 30 * 24 * 3600),
        clock=clock,
    )
    demo.seepnews.posts = [
        Post(
            post_id=p["post_id"],
            agent_id=p.get("agent_id"),
            category=p["category"],
            body=p["body"],
            mentions=p["mentions"],
            hashtags=p.get("hashtags", []),
            timestamp=p["timestamp"],
        )
        for p in sn.get("posts", [])
    ]
    demo.seepnews.hash_db = dict(sn.get("hash_db", {}))
    demo.seepnews._last_post_at = dict(sn.get("last_post_at", {}))
    demo.seepnews._body_locks = {
        fp: (entry["origin"], entry["expires"])
        for fp, entry in sn.get("body_locks", {}).items()
    }

    chain_data = data.get("chain", {})
    demo.chain = SynTrendsChain()
    demo.chain.chain = []
    for bd in chain_data.get("blocks", []):
        txs = [Transaction(t["tx_type"], t["payload"], t["timestamp"]) for t in bd["transactions"]]
        demo.chain.chain.append(
            Block(
                index=bd["index"],
                timestamp=bd["timestamp"],
                transactions=txs,
                previous_hash=bd["previous_hash"],
                nonce=bd.get("nonce", 0),
                hash=bd.get("hash", ""),
            )
        )
    if not demo.chain.chain:
        demo.chain._create_genesis_block()
    demo.chain.pending = [
        Transaction(t["tx_type"], t["payload"], t["timestamp"]) for t in chain_data.get("pending", [])
    ]

    demo.trading = TradingEngine(demo.wallets, demo.fees, demo.chain, clock=clock)
    return demo
