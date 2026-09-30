"""Tax export CSV generation from on-chain trade logs (Phase E sample)."""

from __future__ import annotations

import csv
import io
from typing import Iterable

from chain.engine import SynTrendsDemo


def trades_for_agents(demo: SynTrendsDemo, agent_ids: Iterable[str]) -> list[dict]:
    wanted = set(agent_ids)
    coin_ticker = {c.coin_id: c.ticker for c in demo.coins.values()}
    rows: list[dict] = []

    def _append(block_index: int | str, tx) -> None:
        if tx.tx_type != "trade":
            return
        p = tx.payload
        agent_id = p.get("agent_id")
        if agent_id not in wanted:
            return
        coin_id = p.get("coin_id", "")
        rows.append({
            "datetime": tx.timestamp,
            "agent_id": agent_id,
            "ticker": coin_ticker.get(coin_id, coin_id),
            "side": p.get("side", ""),
            "fiat_amount": p.get("fiat_amount", 0.0),
            "coin_amount": p.get("coin_amount", 0.0),
            "fee": p.get("fee", 0.0),
            "price_after": p.get("price_after", 0.0),
            "block_index": block_index,
            "order_id": p.get("order_id", ""),
        })

    for block_index, tx in demo.chain.all_transactions():
        _append(block_index, tx)

    rows.sort(key=lambda r: r["datetime"])
    return rows


def render_tax_csv(demo: SynTrendsDemo, agent_ids: Iterable[str]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "datetime", "agent_id", "ticker", "side", "fiat_amount", "coin_amount",
        "fee", "price_after", "block_index", "order_id",
    ])
    for row in trades_for_agents(demo, agent_ids):
        writer.writerow([
            row["datetime"], row["agent_id"], row["ticker"], row["side"],
            f"{row['fiat_amount']:.6f}", f"{row['coin_amount']:.6f}",
            f"{row['fee']:.6f}", f"{row['price_after']:.6f}",
            row["block_index"], row["order_id"],
        ])
    writer.writerow([])
    writer.writerow(["DISCLAIMER", "Demo export only — not official tax or 1099-DA documentation"])
    return buf.getvalue()
